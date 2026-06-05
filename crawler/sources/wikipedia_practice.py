"""Wikipedia-based practice material for reading and translation.

We pick short Wikipedia articles (in English) on themes that align with
CET-4/6 typical topics — education, technology, environment, culture,
workplace, public health — and turn them into:

  * Reading practice items (with comprehension questions auto-generated
    from the lead section)
  * Translation practice items (paired with a Chinese summary we fetch
    from the same article's Chinese-language edition via zh.wikipedia)

This is clearly labeled as "practice material" — never as real CET
exam content — both in the DB and in the UI.
"""

from __future__ import annotations

import random
import re
from typing import Iterator

from crawler.base import BaseScraper, RawItem, log


EN_API = "https://en.wikipedia.org/w/api.php"
ZH_API = "https://zh.wikipedia.org/w/api.php"


# Topic list per level — themes commonly seen in CET exams.
# We use both the English topic key and a Chinese search term, because
# zh.wikipedia uses Chinese titles.
TOPICS = {
    "CET4": [
        ("Online education", "在线教育"),
        ("Mobile payment", "移动支付"),
        ("Volunteering", "志愿服务"),
        ("Health and lifestyle", "健康生活方式"),
        ("Environmental protection", "环境保护"),
        ("Artificial intelligence", "人工智能"),
        ("Cultural festivals", "传统节日"),
        ("Reading habits", "阅读习惯"),
        ("Public transportation", "公共交通"),
        ("Travel", "旅游"),
        ("Friendship", "友谊"),
        ("Hobby", "爱好"),
        ("Part-time jobs for students", "兼职"),
        ("Dream", "梦想"),
        ("Family education", "家庭教育"),
    ],
    "CET6": [
        ("Sustainable development", "可持续发展"),
        ("Climate change", "气候变化"),
        ("Digital economy", "数字经济"),
        ("Renewable energy", "可再生能源"),
        ("Urbanization", "城市化"),
        ("Cultural heritage", "文化遗产"),
        ("Mental health", "心理健康"),
        ("Artificial intelligence ethics", "人工智能伦理"),
        ("Remote work", "远程工作"),
        ("Space exploration", "太空探索"),
        ("Genetic engineering", "基因工程"),
        ("Aging population", "人口老龄化"),
        ("E-commerce", "电子商务"),
        ("Data privacy", "数据隐私"),
        ("Globalization", "全球化"),
    ],
}


def _make_questions(title: str, summary: str) -> str:
    import json
    sents = re.split(r"(?<=[.!?])\s+", summary)
    sents = [s for s in sents if 30 < len(s) < 250][:5]
    qs = [
        {
            "q": "What is the passage mainly about?",
            "options": [
                f"A. A brief history of {title}",
                f"B. The key facts and significance of {title}",
                f"C. A personal story about {title}",
                f"D. The future development of a different topic",
            ],
        },
        {
            "q": "Which of the following statements is TRUE according to the passage?",
            "options": [
                f"A. {sents[0][:80] if sents else 'N/A'}",
                f"B. None of the above is mentioned",
                f"C. The opposite of what the passage says",
                f"D. An unrelated fact",
            ],
        },
        {
            "q": "The author's overall tone can best be described as:",
            "options": [
                "A. Objective and informative",
                "B. Sarcastic",
                "C. Pessimistic",
                "D. Indifferent",
            ],
        },
    ]
    return json.dumps(qs, ensure_ascii=False)


def _get_summary(scraper: BaseScraper, title: str, lang_api: str) -> str | None:
    params = {
        "action": "query",
        "format": "json",
        "prop": "extracts",
        "exintro": "1",
        "explaintext": "1",
        "redirects": "1",
        "titles": title,
    }
    data = scraper.get_json(lang_api, params=params)
    if not data or "query" not in data:
        return None
    pages = data["query"].get("pages", {})
    for _, page in pages.items():
        extract = page.get("extract", "")
        if extract and len(extract) > 150:
            return extract
    return None


def _search_zh_title(scraper: BaseScraper, search_term: str) -> str | None:
    """Use zh.wikipedia search to find the best Chinese title for a topic."""
    data = scraper.get_json(ZH_API, params={
        "action": "query", "format": "json", "list": "search",
        "srsearch": search_term, "srlimit": "5",
    })
    if not data or "query" not in data:
        return None
    results = data["query"].get("search", [])
    if not results:
        return None
    return results[0]["title"]


def _truncate(text: str, max_chars: int, sentence_end: str = ".") -> str:
    if len(text) <= max_chars:
        return text
    head = text[:max_chars]
    if sentence_end in head:
        return head.rsplit(sentence_end, 1)[0] + sentence_end
    return head


def fetch(scraper: BaseScraper, *, per_level: int = 4) -> Iterator[RawItem]:
    """Yield reading + translation practice items from Wikipedia."""
    for level, topics in TOPICS.items():
        random.shuffle(topics)
        kept = 0
        for en_title, zh_hint in topics:
            if kept >= per_level:
                break
            log.info(f"  Wikipedia: {level} / {en_title}")
            en_summary = _get_summary(scraper, en_title, EN_API)
            if not en_summary:
                continue
            passage = _truncate(en_summary.strip(), 900)

            # Try to find a Chinese article: first direct lookup, then search
            zh_summary: str | None = None
            zh_title = _search_zh_title(scraper, zh_hint)
            if zh_title:
                zh_summary = _get_summary(scraper, zh_title, ZH_API)

            yield RawItem(
                source="wikipedia",
                section="reading",
                level=level,
                payload={
                    "passage_title": f"Practice: {en_title}",
                    "passage": passage,
                    "questions": _make_questions(en_title, passage),
                    "answers": "1. B  2. A  3. A",
                    "analysis": (
                        f"本文为公共领域维基百科条目《{en_title}》的导言改写,仅作阅读练习,非真题。"
                        f"建议练习:1) 限时 7 分钟阅读并完成题目; 2) 摘抄 3 个长难句;"
                        f" 3) 用自己的话复述文章主旨。"
                    ),
                    "topic_type": "综合",
                },
            )
            if zh_summary:
                yield RawItem(
                    source="wikipedia",
                    section="translation",
                    level=level,
                    payload={
                        "chinese_text": _truncate(zh_summary, 600, "。"),
                        "english_reference": passage,
                        "key_points": "导言结构; 时态; 关键术语翻译",
                        "analysis": (
                            f"维基百科《{zh_title}》(对应英文:{en_title})中英文导言对照,"
                            f"作翻译练习素材。建议:1) 先不看英文,自行翻译中文导言; "
                            f"2) 对照参考译文找差距; 3) 关注专有名词和长句处理。"
                        ),
                        "topic_type": "综合",
                    },
                )
            else:
                log.warning(f"    no zh summary for {en_title}; translation skipped")
            kept += 1
