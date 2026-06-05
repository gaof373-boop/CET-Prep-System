"""Online translation fallback source.

Used by the backfill script to translate English words whose
``translation`` column is empty in the local DB. We try two public
endpoints (no API key needed) and fall back to ``None`` if both fail.

Endpoints:
1. **MyMemory** — ``https://api.mymemory.translated.net/get``
   Free tier: ~5000 chars/day per IP. Returns JSON with
   ``responseData.translatedText``.
2. **Youdao open dict** — ``https://dict.youdao.com/jsonapi``
   Older endpoint that does word-level translation; lightweight.

The fetcher is rate-limited to 1 request per second (configurable) to
be a polite citizen. Network failures are logged and skipped — never
crash the caller.
"""

from __future__ import annotations

import json
import re
import time
from typing import Iterable, Optional

from crawler.base import BaseScraper, RawItem, log


# MyMemory is the most reliable free endpoint; it accepts any string
# for the q= param and returns a clean JSON shape.
MYMEMORY_URL = "https://api.mymemory.translated.net/get"

# Youdao's open dictionary endpoint (no auth needed). It returns
# structured data for word lookups.
YOUDAO_DICT_URL = "https://dict.youdao.com/jsonapi"


def _clean_translation(raw: str) -> str:
    """Strip noise from a translation string and return the meaningful
    Chinese gloss(es).
    """
    if not raw:
        return ""
    s = raw.strip()
    # MyMemory sometimes prefixes "Translated from ..." — strip the
    # whole prefix if present.
    s = re.sub(r"^[^A-Za-z一-鿿]+", "", s).strip()
    # Cap at a reasonable length so the UI doesn't blow up.
    return s[:200]


def _mymemory_lookup(scraper: BaseScraper, word: str) -> Optional[str]:
    """Hit MyMemory's free translation API. Returns Chinese text or None."""
    params = {"q": word, "langpair": "en|zh-CN"}
    data = scraper.get_json(MYMEMORY_URL, params=params)
    if not data:
        return None
    try:
        if data.get("responseStatus") not in (200, "200"):
            return None
        translated = data["responseData"]["translatedText"]
    except (KeyError, TypeError):
        return None
    return _clean_translation(translated)


def _youdao_lookup(scraper: BaseScraper, word: str) -> Optional[str]:
    """Try Youdao's open dict endpoint as a secondary fallback."""
    params = {
        "jsonversion": "1",
        "client": "web",
        "q": word,
    }
    data = scraper.get_json(YOUDAO_DICT_URL, params=params)
    if not data:
        return None
    # The JSON shape varies; try a few common keys.
    parts: list[str] = []
    for key_path in (("ec", "word", 0, "trs", 0, "l", "i", 2),):
        try:
            cur: Any = data
            for k in key_path:
                cur = cur[k]
            if cur:
                parts.append(str(cur))
        except (KeyError, TypeError, IndexError):
            continue
    if parts:
        return _clean_translation(parts[0])
    return None


def translate_word(scraper: BaseScraper, word: str) -> Optional[str]:
    """Try every available endpoint and return the first hit.

    Returns ``None`` on total failure (network down, API blocked, …).
    The returned string is the *Chinese* translation suitable for
    storing in the ``translation`` column.
    """
    if not word or not word.strip():
        return None
    word = word.strip()
    # 1) MyMemory
    res = _mymemory_lookup(scraper, word)
    if res and any("一" <= ch <= "鿿" for ch in res):
        return res
    # 2) Youdao (less reliable, often 403)
    try:
        res = _youdao_lookup(scraper, word)
        if res and any("一" <= ch <= "鿿" for ch in res):
            return res
    except Exception:
        pass
    return None


def translate_many(
    scraper: BaseScraper, words: Iterable[str], *, delay: float = 1.0,
) -> Iterable[tuple[str, Optional[str]]]:
    """Yield ``(word, translation_or_None)`` for every input.

    Rate-limits by sleeping ``delay`` seconds between requests. Logs
    progress every 20 words.
    """
    items = list(words)
    for i, word in enumerate(items):
        if i and delay > 0:
            time.sleep(delay)
        if i % 20 == 0:
            log.info(f"  online_translate: {i}/{len(items)}")
        tr = translate_word(scraper, word)
        yield word, tr
