"""Wiktionary API: enrich existing words with phonetic, translations, and
example sentences. We do NOT pull random words from Wiktionary — we only
look up words we already have on hand (from the GitHub source or local
fallback list). This keeps the vocabulary level appropriate and avoids
drift into obscure terms.
"""

from __future__ import annotations

import re
from typing import Iterable, Iterator

from crawler.base import BaseScraper, RawItem, log


WIKTIONARY_API = "https://en.wiktionary.org/w/api.php"


# IPA characters typically found in Wiktionary pronunciation keys
_IPA_CHARS = set("əɪæʌɔʊʃʒθðɒɜɑɛɪʊŋɲɾɹʔɣχʁħʕʷʲːˈˌ")


def _extract_phonetic(parsed: dict) -> str | None:
    """Find the FIRST IPA pronunciation in the parsed Wiktionary HTML.

    We do a regex scan on the rendered HTML and look for ``/.../``-wrapped
    tokens that look like IPA (contain at least one IPA diacritic or
    phonetic letter).
    """
    try:
        html: str = parsed["parse"]["text"]["*"]
    except (KeyError, TypeError):
        return None
    for m in re.finditer(r"/([^/<>]{2,40})/", html):
        body = m.group(1)
        if any(ch in _IPA_CHARS for ch in body):
            return f"/{body}/"
    return None


def _extract_chinese_gloss(parsed: dict) -> str | None:
    """Try to pull the Chinese-language link title from Wiktionary.

    Wiktionary's langlinks use the key ``*`` for the title (not ``title``).
    Many English entries link to a Chinese page whose title is the same
    English word (e.g. loanwords); we only treat the value as a real
    Chinese translation when the title actually contains CJK characters.
    """
    try:
        langs = parsed.get("parse", {}).get("langlinks", []) or []
    except Exception:
        return None
    for ll in langs:
        if ll.get("lang") in ("zh", "zh-Hans", "zh-CN", "cmn"):
            t = ll.get("*") or ll.get("title")
            if t and any("一" <= ch <= "鿿" for ch in str(t)):
                return str(t)
    return None


def _extract_example(parsed: dict) -> tuple[str, str] | None:
    """Return (english, translation) for the first usage example.

    We scan the HTML for ``<div class="example">...</div>`` blocks; failing
    that we look at ``<li>`` items that look like sentences.
    """
    try:
        html: str = parsed["parse"]["text"]["*"]
    except (KeyError, TypeError):
        return None
    # <div class="example"> blocks
    for m in re.finditer(r'<div[^>]*class="[^"]*example[^"]*"[^>]*>(.+?)</div>',
                         html, re.DOTALL | re.IGNORECASE):
        text = re.sub(r"<[^>]+>", " ", m.group(1))
        text = re.sub(r"\s+", " ", text).strip()
        # Decode common HTML entities
        text = (text.replace("&#33;", "!")
                     .replace("&#63;", "?")
                     .replace("&amp;", "&")
                     .replace("&quot;", '"')
                     .replace("&lt;", "<")
                     .replace("&gt;", ">"))
        if 25 < len(text) < 250:
            return (text, "")
    # <li> usage examples (Wiktionary often uses lists)
    for m in re.finditer(r"<li[^>]*>(.{30,250}?\.)</li>", html, re.DOTALL):
        text = re.sub(r"<[^>]+>", " ", m.group(1))
        text = re.sub(r"\s+", " ", text).strip()
        text = (text.replace("&#33;", "!")
                     .replace("&#63;", "?")
                     .replace("&amp;", "&")
                     .replace("&quot;", '"')
                     .replace("&lt;", "<")
                     .replace("&gt;", ">"))
        if any(kw in text.lower() for kw in ("category", "see also", "redirect")):
            continue
        if 30 < len(text) < 250:
            return (text, "")
    return None


def fetch_for_words(
    scraper: BaseScraper, words: Iterable[tuple[str, str]]
) -> Iterator[RawItem]:
    """Look up each (level, word) pair on Wiktionary; yield only successful
    lookups. ``words`` is an iterable of ``(level, word)`` so we can tag
    the enrichment to the right level (avoiding duplicate-key conflicts).
    """
    pairs = list(words)
    if not pairs:
        return
    for i, (level, word) in enumerate(pairs):
        if i % 25 == 0:
            log.info(f"  Wiktionary: {i}/{len(pairs)}")
        params = {
            "action": "parse",
            "page": word,
            "format": "json",
            "prop": "text|sections|langlinks",
            "redirects": "1",
        }
        data = scraper.get_json(WIKTIONARY_API, params=params)
        if not data or "error" in data or "parse" not in data:
            continue
        phonetic = _extract_phonetic(data)
        zh = _extract_chinese_gloss(data)
        example = _extract_example(data)
        if not (phonetic or zh or example):
            continue
        yield RawItem(
            source="wiktionary",
            section="vocabulary",
            level=level or "shared",
            payload={
                "word": word.lower(),
                "phonetic": phonetic or "",
                "translation": zh or "",
                "example_sentence": example[0] if example else "",
                "example_translation": example[1] if example else "",
            },
        )
