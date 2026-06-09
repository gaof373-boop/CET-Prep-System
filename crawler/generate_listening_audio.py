"""批量为 listening 板块生成配套 .mp3 音频(基于 edge-tts 免 Key)。

工作流
------

1. 读取 listening 表所有非空 ``audio_script`` 行的记录
2. 命名规则: ``database/audio/CET4_YYYY_<id>.mp3``
   (年份取 row['year'];若年份为 0/空则用 'all' 占位)
3. 调 edge-tts 用美式女声 (en-US-AriaNeural,语速 +0%) 合成
4. 跳过已存在且大小 > 0 的文件(断点续传)
5. 合成完成后 UPDATE listening.audio_file = 路径
6. 全部跑完打印统计报告

用法
----
::

    python -m crawler.generate_listening_audio
    python -m crawler.generate_listening_audio --voice en-US-GuyNeural  # 美男声
    python -m crawler.generate_listening_audio --rate "-10%" --limit 5    # 测试 5 条
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

# Make project root importable
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.db_init import init_database  # noqa: E402
from core.data_manager import DataManager  # noqa: E402

AUDIO_DIR = ROOT / "database" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# Voice split defaults — edge-tts voice IDs, not OpenAI nova/shimmer.
# These are the standard "clear American female / warm American male" pair.
VOICE_WOMAN = "en-US-AriaNeural"
VOICE_MAN = "en-US-GuyNeural"

# Regex: line that starts (at line start, with optional leading space) with
# W: or M: followed by content. Case-insensitive on the tag.
SPEAKER_RE = re.compile(r"^\s*([WM]):\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
# Stray speaker tags that appear mid-paragraph (no leading ^). Rare, but
# strip them so the TTS doesn't literally read "W colon".
INLINE_SPEAKER_RE = re.compile(r"\b[WM]:\s*", re.IGNORECASE)


def _safe_filename(level: str, year: int, item_id: int) -> str:
    """Build a deterministic filename: ``CET4_2024_12.mp3``.

    We append the row's id as a tie-breaker so two rows for the
    same (level, year, session) don't collide.
    """
    if not year or year == 0:
        year_part = "all"
    else:
        year_part = str(year)
    return f"{level}_{year_part}_{item_id}.mp3"


def _split_speakers(text: str) -> list[tuple[str, str]]:
    """Split a dialogue script into (speaker, line) tuples.

    Returns an empty list if the text has no W:/M: tags at all — caller
    should fall back to single-voice synthesis in that case.

    Lines without a recognised tag are dropped (they're usually narration
    headings like "Question 1:") — if you want them read aloud, leave them
    tagged or use --voice-split=off.
    """
    matches = SPEAKER_RE.findall(text)
    out: list[tuple[str, str]] = []
    for tag, line in matches:
        speaker = "W" if tag.upper() == "W" else "M"
        line = INLINE_SPEAKER_RE.sub("", line).strip()
        if line:
            out.append((speaker, line))
    return out


async def _synth_one(voice: str, rate: str, text: str, out_path: Path) -> None:
    """Single-voice synthesis (fallback for rows without W:/M: tags)."""
    import edge_tts  # heavy import, only when actually synthesising

    # Strip stray inline tags so TTS doesn't say "W colon".
    cleaned = INLINE_SPEAKER_RE.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if not cleaned:
        return

    comm = edge_tts.Communicate(cleaned, voice=voice, rate=rate)
    await comm.save(str(out_path))


async def _synth_multi_voice(
    rate: str, text: str, out_path: Path,
    voice_w: str = VOICE_WOMAN, voice_m: str = VOICE_MAN,
) -> None:
    """Per-line TTS with woman/man voice alternation, then byte-concat.

    Falls back to single-voice (woman by default) if the text has no
    recognisable W:/M: tags at all. This keeps backward-compat for
    monologue-style listening passages.

    Naive byte-concat works because edge-tts encodes both voices at
    identical bitrate / sample-rate, and each MPEG-1 Layer 3 frame is
    self-contained (carries its own sync + header). No ffmpeg / pydub
    dependency needed.
    """
    import edge_tts  # heavy import, only when actually synthesising

    lines = _split_speakers(text)
    if not lines:
        # No dialogue structure — treat as monologue with the woman voice
        # (historical default).
        await _synth_one(voice_w, rate, text, out_path)
        return

    voice_map = {"W": voice_w, "M": voice_m}
    audio_blobs: list[bytes] = []
    for speaker, line in lines:
        comm = edge_tts.Communicate(line, voice=voice_map[speaker], rate=rate)
        chunks: list[bytes] = []
        async for ev in comm.stream():
            if ev["type"] == "audio":
                chunks.append(ev["data"])
        if chunks:
            audio_blobs.append(b"".join(chunks))

    if not audio_blobs:
        # All lines produced nothing — shouldn't happen, but be defensive.
        await _synth_one(voice_w, rate, text, out_path)
        return

    out_path.write_bytes(b"".join(audio_blobs))


def _synth_split_sync(rate: str, text: str, out_path: Path) -> None:
    """Thread-safe wrapper for the multi-voice path."""
    asyncio.run(_synth_multi_voice(rate, text, out_path))


def _synth_sync(voice: str, rate: str, text: str, out_path: Path) -> None:
    """Thread-safe wrapper that runs the async TTS in a private loop."""
    asyncio.run(_synth_one(voice, rate, text, out_path))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="批量生成 listening 配套 .mp3 音频"
    )
    parser.add_argument("--voice", default="en-US-AriaNeural",
                        help="edge-tts 声音 ID (默认美式女声 Aria)")
    parser.add_argument("--rate", default="+0%",
                        help="edge-tts 语速,例如 '+0%' '-10%' '+20%'")
    parser.add_argument("--level", choices=["CET4", "CET6"],
                        help="只生成一个级别 (默认两个都生成)")
    parser.add_argument("--limit", type=int, default=0,
                        help="最多处理多少条 (0=无限制,默认)")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印计划,不真生成")
    parser.add_argument("--voice-split", choices=["on", "off"], default="on",
                        help="是否按 W:/M: 切分男女声 (默认 on);off 则用 --voice 单声")
    args = parser.parse_args()

    init_database()
    dm = DataManager()

    levels = [args.level] if args.level else ["CET4", "CET6"]
    total_planned = 0
    total_done = 0
    total_skipped = 0
    total_failed = 0
    for level in levels:
        rows = dm.list_listening(level)
        if args.limit:
            rows = rows[: args.limit]
        print(f"\n{'=' * 60}")
        print(f"  🎙️  {level}  共 {len(rows)} 条 listening 记录")
        print(f"  模式: {'男女声切分 (W=Aria / M=Guy)' if args.voice_split == 'on' else '单声 ' + args.voice}")
        print(f"{'=' * 60}")
        for r in rows:
            text = (r.get("audio_script") or "").strip()
            if not text:
                print(f"  · id={r['id']}  (空 audio_script, 跳过)")
                continue
            fname = _safe_filename(level, int(r.get("year") or 0), int(r["id"]))
            out_path = AUDIO_DIR / fname
            # 也存到 DB 字段 (相对路径)
            rel_path = f"database/audio/{fname}"
            if out_path.exists() and out_path.stat().st_size > 0:
                # Make sure DB also reflects the path (use a fresh conn
                # — the main dm._conn() may still hold a write tx).
                if r.get("audio_file") != rel_path:
                    try:
                        with dm._conn() as c:  # type: ignore[attr-defined]
                            c.execute(
                                "UPDATE listening SET audio_file = ? "
                                "WHERE id = ?",
                                (rel_path, r["id"]),
                            )
                            c.commit()
                    except Exception as e:
                        print(f"  ⚠ id={r['id']}  DB 更新 audio_file 失败: {e}")
                print(f"  ↻ id={r['id']:>3d}  {fname}  (已存在 {out_path.stat().st_size//1024}KB,跳过)")
                total_skipped += 1
                continue
            total_planned += 1
            if args.dry_run:
                # show what we'd do
                if args.voice_split == "on":
                    lines = _split_speakers(text)
                    w = sum(1 for s, _ in lines if s == "W")
                    m = sum(1 for s, _ in lines if s == "M")
                    tag_info = f"W×{w} M×{m}" if lines else "无标签(单声)"
                else:
                    tag_info = "单声"
                print(f"  📝 id={r['id']:>3d}  -> {fname}  ({len(text)} chars, {tag_info})  [dry-run]")
                continue
            try:
                if args.voice_split == "on":
                    _synth_split_sync(args.rate, text, out_path)
                else:
                    _synth_sync(args.voice, args.rate, text, out_path)
                size_kb = out_path.stat().st_size // 1024
                try:
                    with dm._conn() as c:  # type: ignore[attr-defined]
                        c.execute(
                            "UPDATE listening SET audio_file = ? "
                            "WHERE id = ?",
                            (rel_path, r["id"]),
                        )
                        c.commit()
                except Exception as e:
                    print(f"  ⚠ id={r['id']}  DB 更新 audio_file 失败: {e}")
                voice_info = "split" if args.voice_split == "on" else args.voice
                print(f"  ✅ id={r['id']:>3d}  {fname}  ({size_kb}KB, voice={voice_info})")
                total_done += 1
            except Exception as e:
                print(f"  ❌ id={r['id']:>3d}  {fname}  失败: {e}")
                total_failed += 1

    print()
    print("=" * 60)
    print("  ✅  音频批量生成完成")
    print("=" * 60)
    print(f"  计划生成:  {total_planned}")
    print(f"  成功生成:  {total_done}")
    print(f"  跳过(已存在): {total_skipped}")
    print(f"  失败:      {total_failed}")
    print(f"  音频目录:  {AUDIO_DIR}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())