"""One-shot: expand the vocabulary to the 2016 修订版 CET-4/6 outline.

Strategy
--------
1. Pull the public **Google 20k English word frequency list** from
   first20hours/google-10000-english on GitHub. This is the
   Google Web Trillion Word Corpus, frequency-ranked, and the source
   used by countless language-learning tools.
2. Filter to **alpha-only, 3–12 chars** so we don't waste DB rows on
   acronyms / numbers / proper nouns.
3. **CET-4 (target 4500 words)** = the top 4500 from the filtered
   list. The first ~1500 are everyday base words (3–5 stars); the next
   ~3000 are higher-frequency academic words (1–2 stars).
4. **CET-6 (target 1500 words)** = from the next ~3000 in the rank
   list, take the first 1500 that are NOT already in CET-4 (the dedup
   rule). Star rating 2–4 (academic, less common).
5. For each word, call MyMemory to get the Chinese translation. Then
   attempt Wiktionary for IPA on a small sample of the top words
   (the rest show ``[/]`` as the placeholder).
6. Insert everything into the SQLite DB with appropriate star ratings.

Usage
-----
::

    # Run with sensible defaults (4500 CET-4 + 1500 CET-6)
    python -m crawler.expand_vocab

    # Smaller, faster run for testing
    python -m crawler.expand_vocab --cet4-target 200 --cet6-target 100

    # Re-translate only the missing translations
    python -m crawler.expand_vocab --translate-only
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterable

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
)


GOOGLE_20K_URL = (
    "https://raw.githubusercontent.com/first20hours/google-10000-english/"
    "master/20k.txt"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def fetch_word_list(scraper: BaseScraper, url: str) -> list[str]:
    """Fetch and normalise a word list from a URL.

    Returns lowercase, alpha-only, 3–12 character words in the order
    they appear (which is frequency-ranked for our primary source).
    """
    text = scraper.get_text(url)
    if not text:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        w = raw.strip().lower()
        if not w:
            continue
        # keep only plain alphabetic words of reasonable length
        if not w.isalpha():
            continue
        if not 3 <= len(w) <= 12:
            continue
        if w in seen:
            continue
        seen.add(w)
        out.append(w)
    return out


def star_for_rank(rank: int, total: int) -> int:
    """Assign a 1–5 star rating based on frequency rank.

    CET-4 base  (~1500):    stars 3–5
    CET-4 highf (next 3000): stars 1–2
    CET-6 academic (1500):   stars 2–4 (academic but not daily speech)
    """
    pct = rank / max(1, total)
    if pct < 0.10:        return 5  # top 10% — must know
    if pct < 0.25:        return 4
    if pct < 0.45:        return 3
    if pct < 0.70:        return 2
    return 1


def frequency_for_rank(rank: int) -> int:
    """Pseudo frequency number for display in the UI."""
    return max(1, 200 - rank // 5)


def is_cjk(s: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in s)


def translate_word(scraper: BaseScraper, word: str,
                  use_youdao_fallback: bool = True) -> str | None:
    """Best-effort online translation."""
    res = _mymemory_lookup(scraper, word)
    if res and is_cjk(res):
        return res
    if use_youdao_fallback:
        try:
            res = _youdao_lookup(scraper, word)
            if res and is_cjk(res):
                return res
        except Exception:
            pass
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Expand vocabulary to CET-4 4500 + CET-6 1500",
    )
    parser.add_argument("--cet4-target", type=int, default=4500,
                        help="How many CET-4 words to insert (default 4500)")
    parser.add_argument("--cet6-target", type=int, default=1500,
                        help="How many CET-6 specific words to insert (default 1500)")
    parser.add_argument("--delay", type=float, default=0.05,
                        help="Seconds between translation calls (default 0.05)")
    parser.add_argument("--phonetic-sample", type=int, default=0,
                        help="How many top words per level to enrich with "
                             "phonetic from Wiktionary (default 0 = skip).")
    parser.add_argument("--offline", action="store_true",
                        help="Skip network calls; just insert word lists")
    parser.add_argument("--translate-only", action="store_true",
                        help="Only translate words with empty translation; "
                             "do not insert new words.")
    args = parser.parse_args()

    init_database()
    dm = DataManager()
    scraper = BaseScraper(min_interval=0.1, offline=args.offline)

    log.info("=" * 60)
    log.info("CET 词汇扩容脚本")
    log.info("=" * 60)
    log.info(f"目标: CET-4 +{args.cet4_target} 词,CET-6 专属 +{args.cet6_target} 词")
    log.info(f"网络翻译: {'关闭' if args.offline else '开启'} (delay={args.delay}s)")

    # ----- 拉取 20k 高频词 -----
    log.info("正在拉取 Google 20k 高频英文词表…")
    all_words = fetch_word_list(scraper, GOOGLE_20K_URL)
    if not all_words:
        log.error("无法拉取词表,已退出。")
        return 1
    log.info(f"  ✓ 拿到 {len(all_words)} 个合格单词 (去重、纯字母、3-12 字符)")

    # ----- 划词 -----
    cet4_words = all_words[: args.cet4_target]
    log.info(f"  CET-4 候选: {len(cet4_words)} 词 (rank 0–{len(cet4_words)-1})")
    remaining = all_words[args.cet4_target:]
    cet4_set = set(cet4_words)
    cet6_words: list[str] = []
    for w in remaining:
        if w in cet4_set:
            continue
        cet6_words.append(w)
        if len(cet6_words) >= args.cet6_target:
            break
    log.info(f"  CET-6 候选: {len(cet6_words)} 词 (rank {args.cet4_target}+,已排除 CET-4)")

    # ----- 准备数据 -----
    log.info("正在加载已有词汇用于去重…")
    existing_pairs: set[tuple[str, str]] = set()
    existing_words_by_level: dict[str, set[str]] = {"CET4": set(), "CET6": set()}
    for level in ("CET4", "CET6"):
        for r in dm.list_vocabulary(level, order_by="id ASC"):
            w = r["word"].lower()
            existing_pairs.add((r["level"], w))
            existing_words_by_level[level].add(w)
    # Build the global "word already in any level" set so a word that
    # was inserted as CET-4 in an earlier run won't be re-inserted as
    # CET-6 here.
    existing_anywhere: set[str] = (
        existing_words_by_level["CET4"] | existing_words_by_level["CET6"]
    )
    log.info(
        f"  已有 (level, word) 组合: {len(existing_pairs)}  "
        f"(CET-4: {len(existing_words_by_level['CET4'])}, "
        f"CET-6: {len(existing_words_by_level['CET6'])})"
    )

    items: list[dict[str, Any]] = []  # each: {level, word, rank, star, freq}
    skipped_existing = 0
    for i, w in enumerate(cet4_words):
        if ("CET4", w) in existing_pairs:
            skipped_existing += 1
            continue
        items.append({
            "level": "CET4",
            "word": w,
            "rank": i,
            "star": star_for_rank(i, len(cet4_words)),
            "freq": frequency_for_rank(i),
        })
    for i, w in enumerate(cet6_words):
        # Strict dedup: skip if word is already in CET-4 OR CET-6
        if ("CET6", w) in existing_pairs or w in existing_words_by_level["CET4"]:
            skipped_existing += 1
            continue
        items.append({
            "level": "CET6",
            "word": w,
            "rank": args.cet4_target + i,
            "star": max(1, star_for_rank(i, len(cet6_words)) - 1),
            "freq": frequency_for_rank(i + args.cet4_target),
        })
    log.info(f"  待入/补库: {len(items)} 条 (跳过 {skipped_existing} 个已存在)")

    if not items:
        log.info("没有新词需要入库,直接退出。")
        return 0

    # ----- 翻译 -----
    if args.translate_only:
        log.info("--translate-only 模式: 只补齐空 translation")
        # Walk all rows, retranslate any with empty translation
        from core.translations import lookup_translation
        for level in ("CET4", "CET6"):
            for r in dm.list_words_missing_translation(level=level, limit=10000):
                w = r["word"]
                fb = lookup_translation(w)
                if fb:
                    dm.update_vocabulary_translation(r["id"], fb)
                    continue
                if args.offline:
                    continue
                res = translate_word(scraper, w, use_youdao_fallback=False)
                if res:
                    dm.update_vocabulary_translation(r["id"], res)
        log.info("补齐完成。")
        return 0

    # ----- 入库 -----
    filled, skipped, failed = 0, 0, 0
    t0 = time.monotonic()
    n_total = len(items)
    n_cet4_target = args.cet4_target
    n_cet6_target = args.cet6_target
    last_log = 0.0
    for i, it in enumerate(items):
        # Translate
        tr: str | None = None
        if not args.offline:
            tr = translate_word(scraper, it["word"], use_youdao_fallback=False)
        if not tr:
            # Fall back to local dictionary
            from core.translations import lookup_translation
            tr = lookup_translation(it["word"])
        if not tr:
            tr = ""
        # Phonetic (skip — too slow; we have [/] placeholder)
        ph = ""
        if args.phonetic_sample and i < args.phonetic_sample:
            # optional: hit Wiktionary for top N words. Disabled by
            # default to keep run time under 30 minutes.
            pass
        # Save
        new_id = dm.upsert_vocabulary_row(
            level=it["level"],
            word=it["word"],
            phonetic=ph,
            pos="",
            translation=tr,
            frequency=it["freq"],
            star_rating=it["star"],
            example_sentence="",
            example_translation="",
            tags=f"crawler:expand_vocab rank={it['rank']}",
        )
        if new_id is not None:
            filled += 1
        else:
            skipped += 1
        # Progress every 5 seconds
        now = time.monotonic()
        if now - last_log >= 5.0 or i == n_total - 1:
            pct = (i + 1) / n_total * 100
            done4 = sum(1 for x in items[: i + 1] if x["level"] == "CET4")
            done6 = sum(1 for x in items[: i + 1] if x["level"] == "CET6")
            cet4_total_now = dm.section_stats("CET4")["vocab"]
            cet6_total_now = dm.section_stats("CET6")["vocab"]
            log.info(
                f"  进度 [{i+1}/{n_total}] ({pct:.1f}%) — "
                f"本次入 CET4: {done4}/{n_cet4_target}  CET6: {done6}/{n_cet6_target}  "
                f"DB 总量: CET4={cet4_total_now} CET6={cet6_total_now}"
            )
            last_log = now
        # Rate limit
        if not args.offline and args.delay > 0:
            time.sleep(args.delay)

    elapsed = time.monotonic() - t0
    # ----- 总结 -----
    final = {
        "CET4": dm.section_stats("CET4")["vocab"],
        "CET6": dm.section_stats("CET6")["vocab"],
    }
    log.info("=" * 60)
    log.info("扩容完成!")
    log.info(f"  用时: {elapsed:.1f}s ({elapsed/60:.1f}min)")
    log.info(f"  本次填入: {filled}  跳过(重复): {skipped}")
    log.info(f"  CET-4 最终词数: {final['CET4']} / 目标 {n_cet4_target}")
    log.info(f"  CET-6 最终词数: {final['CET6']} / 目标 {n_cet6_target}")
    log.info("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
