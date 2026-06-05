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


async def _synth_one(voice: str, rate: str, text: str, out_path: Path) -> None:
    import edge_tts  # heavy import, only when actually synthesising

    # Strip the W:/M: speaker tags we have in some DB rows so the TTS
    # doesn't literally read "W colon".
    cleaned = re.sub(r"^[WwMm]:\s*", "", text, flags=re.MULTILINE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if not cleaned:
        return

    comm = edge_tts.Communicate(cleaned, voice=voice, rate=rate)
    await comm.save(str(out_path))


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
                print(f"  📝 id={r['id']:>3d}  -> {fname}  ({len(text)} chars)  [dry-run]")
                continue
            try:
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
                print(f"  ✅ id={r['id']:>3d}  {fname}  ({size_kb}KB, voice={args.voice})")
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