"""Crawler entry point.

Usage
-----
    python -m crawler.run                       # default: try all sources
    python -m crawler.run --offline             # skip network, use only synthetic
    python -m crawler.run --vocab-only          # only run vocabulary sources
    python -m crawler.run --skip-wiktionary     # don't hit Wiktionary (faster)
    python -m crawler.run --wiki-count N        # how many articles per level
    python -m crawler.run --wiktionary-limit N  # max words to look up
"""

from __future__ import annotations

import argparse
import time
from collections import Counter
from pathlib import Path
import sys

# Make project root importable
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crawler.base import BaseScraper, log  # noqa: E402
from crawler.db_writer import DBWriter  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="CET Prep System — data crawler")
    parser.add_argument("--offline", action="store_true",
                        help="Skip all network calls; use synthetic data only.")
    parser.add_argument("--vocab-only", action="store_true",
                        help="Only run vocabulary sources.")
    parser.add_argument("--skip-wiktionary", action="store_true",
                        help="Don't enrich words via Wiktionary.")
    parser.add_argument("--wiki-count", type=int, default=6,
                        help="Wikipedia practice items per level (default 6).")
    parser.add_argument("--wiktionary-limit", type=int, default=120,
                        help="Max words to look up on Wiktionary (default 120).")
    parser.add_argument("--interval", type=float, default=1.0,
                        help="Seconds between HTTP calls (default 1).")
    args = parser.parse_args()

    t0 = time.monotonic()
    log.info("=" * 60)
    log.info(f"CET Prep crawler starting (offline={args.offline})")
    log.info("=" * 60)

    scraper = BaseScraper(
        min_interval=args.interval,
        offline=args.offline,
    )
    writer = DBWriter()
    summary: Counter = Counter()
    by_source: Counter = Counter()

    # 1. Quick connectivity test
    network_ok = True
    if not args.offline:
        network_ok = scraper.network_ok()
        log.info(f"Network reachable: {network_ok}")
        if not network_ok:
            log.warning("Network test failed — skipping all HTTP sources, "
                        "using local fallback + synthetic only.")

    # 2. Vocabulary
    log.info("--- VOCABULARY ---")
    words_by_level: dict[str, list[str]] = {"CET4": [], "CET6": []}
    try:
        from crawler.sources import github_vocab
        # Patch the scraper into offline mode if network is down so
        # github_vocab's internal get() calls return None immediately
        # instead of waiting 15s × retries on each candidate URL.
        if not network_ok:
            scraper.offline = True
        for item in github_vocab.fetch(scraper):
            writer.write(item)
            summary[("vocabulary", item.level)] += 1
            by_source[item.source] += 1
            if item.payload.get("word"):
                words_by_level.setdefault(item.level, []).append(item.payload["word"])
    except Exception as e:  # noqa: BLE001
        log.error(f"github_vocab failed: {e}")

    # 3. Wiktionary enrichment (skipped if no network)
    if not args.skip_wiktionary and network_ok and not args.offline:
        log.info("--- WIKTIONARY (enrich) ---")
        try:
            from crawler.sources import wiktionary
            # Build (level, word) pairs so enrichment targets the right level
            pairs: list[tuple[str, str]] = []
            for lvl, words in words_by_level.items():
                for w in words:
                    pairs.append((lvl, w))
            # Cap total lookups
            pairs = pairs[: args.wiktionary_limit]
            for item in wiktionary.fetch_for_words(scraper, pairs):
                writer.write(item)
                summary[("vocabulary", item.level)] += 1
                by_source[item.source] += 1
        except Exception as e:  # noqa: BLE001
            log.error(f"wiktionary failed: {e}")
    else:
        log.info("--- WIKTIONARY (skipped, no network) ---")

    if not args.vocab_only:
        # 4. Wikipedia practice material (skipped if no network)
        if network_ok and not args.offline:
            log.info("--- WIKIPEDIA (reading + translation) ---")
            try:
                from crawler.sources import wikipedia_practice
                for item in wikipedia_practice.fetch(scraper, per_level=args.wiki_count):
                    writer.write(item)
                    summary[(item.section, item.level)] += 1
                    by_source[item.source] += 1
            except Exception as e:  # noqa: BLE001
                log.error(f"wikipedia failed: {e}")
        else:
            log.info("--- WIKIPEDIA (skipped, no network) ---")

        # 5. Synthetic (listening + writing) — always run
        log.info("--- SYNTHETIC (listening + writing) ---")
        try:
            from crawler.sources import synthetic
            for item in synthetic.fetch(scraper):
                writer.write(item)
                summary[(item.section, item.level)] += 1
                by_source[item.source] += 1
        except Exception as e:  # noqa: BLE001
            log.error(f"synthetic failed: {e}")

    # ---- report ----
    elapsed = time.monotonic() - t0
    log.info("=" * 60)
    log.info(f"Done in {elapsed:.1f}s.  Inserted: {writer._inserted}  "
             f"Skipped: {writer._skipped}")
    log.info("By section/level:")
    for (sec, lvl), n in sorted(summary.items()):
        log.info(f"  {sec:>12s} / {lvl:<5s}: {n}")
    log.info("By source:")
    for src, n in sorted(by_source.items()):
        log.info(f"  {src:>12s}: {n}")
    log.info("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
