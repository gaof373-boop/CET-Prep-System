"""One-shot script: backfill missing vocabulary translations via online APIs.

Usage::

    # Backfill all levels, up to 500 words (default)
    python -m crawler.backfill_translations

    # Only CET-4
    python -m crawler.backfill_translations --level CET4

    # More words, faster (0.5s between calls — risky for rate limits)
    python -m crawler.backfill_translations --limit 2000 --delay 0.5
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote
from typing import Optional

# Make project root importable
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.db_init import init_database  # noqa: E402
from core.data_manager import DataManager  # noqa: E402
from crawler.base import BaseScraper, log  # noqa: E402
from crawler.sources.online_translate import (  # noqa: E402
    _mymemory_lookup,
    _youdao_lookup,
    _clean_translation,
)


def is_cjk(s: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in (s or ""))


# ---------------------------------------------------------------------------
# Extra free translation endpoints (no API key required).
# Used in addition to MyMemory/Youdao when those are rate-limited.
# ---------------------------------------------------------------------------
TRANSLATE_FREE_ENDPOINTS = [
    # (url, json_key_chain)  — chain is a list of keys to walk to
    # extract the translated string.
    (
        "https://lingva.ml/api/v1/en/zh/{word}",
        ["translation"],
    ),
    (
        "https://translate.googleapis.com/translate_a/single"
        "?client=gtx&sl=en&tl=zh-CN&dt=t&q={word}",
        ["0", 0, 0],  # nested: data[0][0][0]
    ),
]


def _extra_translate(scraper: BaseScraper, word: str) -> Optional[str]:
    """Try the free Google Translate / Lingva endpoints. Each is hit
    exactly once — no retries, no 429 drain."""
    for url_tpl, key_chain in TRANSLATE_FREE_ENDPOINTS:
        url = url_tpl.format(word=quote(word))
        try:
            if "translate.googleapis.com" in url:
                # Google returns an array, not JSON object.
                data = scraper.session.get(  # type: ignore[union-attr]
                    url, timeout=8,
                ).json() if scraper.session else None
            else:
                data = scraper.get_json(url)
            if not data:
                continue
            cur = data
            for k in key_chain:
                try:
                    cur = cur[k]
                except (KeyError, TypeError, IndexError):
                    cur = None
                    break
            if isinstance(cur, str) and is_cjk(cur):
                return cur[:200]
        except Exception:
            continue
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill missing vocabulary translations via online APIs",
    )
    parser.add_argument("--level", choices=["CET4", "CET6"],
                        help="Only backfill one level (default: both)")
    parser.add_argument("--limit", type=int, default=500,
                        help="Maximum words to backfill per run (default 500)")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Seconds between API calls (default 1.0)")
    parser.add_argument("--offline", action="store_true",
                        help="Skip network calls; just report counts")
    args = parser.parse_args()

    init_database()
    dm = DataManager()
    scraper = BaseScraper(
        min_interval=args.delay,
        timeout=8.0,
        max_retries=1,  # 429 should NOT trigger 17s × 3 retry drain
        offline=args.offline,
    )

    # Check network connectivity — use the MyMemory endpoint itself
    # (wikipedia may be blocked from some networks even when MyMemory
    # works fine, so we test the actual endpoint we need).
    if not args.offline:
        if not scraper.network_ok("https://api.mymemory.translated.net"):
            log.warning("网络不可达,回填已跳过。仅做统计。")
            args.offline = True

    # Print current state
    if args.level:
        n_missing = dm.count_missing_translations(args.level)
        n_total = sum(1 for _ in dm._conn().execute(
            "SELECT 1 FROM vocabulary WHERE level = ?", (args.level,)
        ))
    else:
        n_missing = dm.count_missing_translations()
        n_total = sum(1 for _ in dm._conn().execute("SELECT 1 FROM vocabulary"))
    log.info(f"数据库共 {n_total} 词,其中 {n_missing} 词 translation 为空")

    if args.offline or n_missing == 0:
        log.info("无需回填,退出。")
        return 0

    # Pull the rows we need to fill
    rows = dm.list_words_missing_translation(level=args.level, limit=args.limit)
    log.info(f"本次准备回填 {len(rows)} 词 (limit={args.limit}, delay={args.delay}s)")

    # Translate
    t0 = time.monotonic()
    filled = 0
    failed = 0
    skipped_429 = 0
    cache: dict[str, str | None] = {}

    def _try_translate(w: str) -> Optional[str]:
        """Try MyMemory → Youdao → Lingva → Google Translate.
        Returns ``None`` on total failure; returns "SKIP_429" to tell
        the caller to abandon further lookups for this session."""
        if w in cache:
            return cache[w]
        # 1) MyMemory
        try:
            tr = _mymemory_lookup(scraper, w)
            if tr and is_cjk(tr):
                cache[w] = tr
                return tr
        except Exception:
            pass
        # 2) Youdao (often 403, harmless)
        try:
            tr = _youdao_lookup(scraper, w)
            if tr and is_cjk(tr):
                cache[w] = tr
                return tr
        except Exception:
            pass
        # 3) Free alternatives
        tr = _extra_translate(scraper, w)
        cache[w] = tr
        return tr

    for i, row in enumerate(rows):
        word = row["word"]
        translation = _try_translate(word)
        if translation:
            ok = dm.update_vocabulary_translation(row["id"], translation)
            if ok:
                filled += 1
                if filled <= 5 or filled % 25 == 0:
                    log.info(f"  ✓ {word:<14s} → {translation}")
            else:
                failed += 1
        else:
            failed += 1
            if failed <= 3:
                log.warning(f"  ✗ {word}: 翻译失败")
        if (i + 1) % 20 == 0:
            elapsed = time.monotonic() - t0
            log.info(
                f"  进度 {i+1}/{len(rows)}, 已填 {filled}, 失败 {failed}, "
                f"用时 {elapsed:.0f}s"
            )
        # Rate limit
        if not args.offline and args.delay > 0:
            time.sleep(args.delay)

    elapsed = time.monotonic() - t0
    log.info("=" * 50)
    log.info(f"回填完成: 用时 {elapsed:.1f}s, 填入 {filled}, 失败 {failed}")
    log.info(f"剩余 {n_missing - filled} 词仍待翻译 (可重新运行此脚本增量回填)")
    log.info("=" * 50)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
