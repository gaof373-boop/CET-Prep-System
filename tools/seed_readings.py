"""Seed real-exam-style CET-4/6 reading passages into cet_exam.db.

Idempotent: re-running clears the existing reading rows and re-fills
them. Each pass calls DeepSeek to produce 10 CET-4 + 10 CET-6
passages in 4-5 paragraphs, ~350 words, with 5 standard A/B/C/D
comprehension questions each. Articles are tagged "AI 原创" in the
title and have year=2023 or 2024 so they sit alongside other exam-
year entries without being mistaken for actual CET paper items.

Usage:
    DEEPSEEK_API_KEY=sk-... python tools/seed_readings.py
or:
    python tools/seed_readings.py --key sk-...   (dev only)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

# Make project root importable so we can use DataManager
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402
from core.db_init import DB_PATH  # noqa: E402


# ---------------------------------------------------------------------------
# Topics: 10 per level — broad enough to cover real-exam breadth
# ---------------------------------------------------------------------------
CET4_TOPICS = [
    ("The Psychology of Online Learning",
     "心理学", 2024, "6月",
     "How digital tools are reshaping student engagement and "
     "motivation in higher education."),
    ("Why Walking Improves Creative Thinking",
     "心理/生活", 2023, "12月",
     "New research on the link between physical movement and "
     "divergent problem-solving in knowledge work."),
    ("The Return of the Four-Day Work Week",
     "职场", 2024, "6月",
     "After pandemic-era experiments, companies in Europe and "
     "Asia are quietly adopting compressed schedules."),
    ("How Microplastics Reach the Deep Ocean",
     "环境", 2023, "12月",
     "A new study traces the path of plastic particles from "
     "everyday products to the Mariana Trench."),
    ("The Quiet Revolution in Adult Literacy",
     "教育", 2024, "12月",
     "Why more working adults in their 30s and 40s are returning "
     "to formal classroom learning."),
    ("City Trees and the Urban Heat Island",
     "环境/城市", 2024, "6月",
     "How strategic planting of street trees measurably lowers "
     "summer afternoon temperatures in dense neighborhoods."),
    ("The Rise of Subscription-Based Education",
     "教育", 2023, "12月",
     "Why flat-fee learning apps are challenging the traditional "
     "pay-per-course model across Asia."),
    ("Should Companies Pay You to Exercise?",
     "职场", 2024, "12月",
     "Workplace wellness programs that pay employees for gym "
     "visits and step counts are spreading — what does the "
     "evidence show?"),
    ("Why Boredom Is Good for Your Brain",
     "心理学", 2023, "6月",
     "Neuroscience suggests that periods of doing nothing are "
     "essential for memory consolidation and creative insight."),
    ("The Hidden Cost of Always-On Notifications",
     "心理/生活", 2024, "6月",
     "Constant pings from our phones are reshaping attention "
     "spans in ways that researchers are only beginning to map."),
]

CET6_TOPICS = [
    ("Algorithmic Bias in Hiring Tools",
     "社会/科技", 2024, "6月",
     "How AI resume screeners can quietly filter out qualified "
     "candidates, and what regulators are doing about it."),
    ("The Economics of Urban Green Corridors",
     "环境/城市", 2023, "12月",
     "Why cities from Paris to Singapore are turning disused "
     "rail lines into linear parks for measurable health gains."),
    ("The Long Tail of Childhood Sleep Deprivation",
     "健康/心理", 2024, "6月",
     "Research connecting early school start times to lifetime "
     "productivity and mental-health outcomes."),
    ("Can Central Bank Digital Currencies Save Cross-Border Payments?",
     "经济/金融", 2023, "12月",
     "Pilot programs in Asia suggest CBDCs may finally crack the "
     "decades-old correspondent-banking bottleneck."),
    ("The Forgotten Craft of Manuscript Restoration",
     "文化/教育", 2024, "12月",
     "Inside the small labs where centuries-old texts are being "
     "chemically unwound so the next generation can read them."),
    ("Why Your City Wants to Be a 15-Minute City",
     "社会/城市", 2024, "6月",
     "The urban planning idea putting daily essentials within a "
     "short walk is reshaping zoning debates from Paris to Portland."),
    ("The Coming Backlash Against Always-On Surveillance at Work",
     "职场/科技", 2023, "12月",
     "Bossware that tracks mouse movements and screenshots every "
     "five minutes is facing new legal challenges in three continents."),
    ("What Neuroscience Is Teaching Us About Bilingual Aging",
     "健康/语言", 2024, "6月",
     "New longitudinal data show that speaking two languages "
     "daily measurably delays symptoms of cognitive decline."),
    ("The Hidden Carbon Math of Cloud Computing",
     "环境/科技", 2023, "12月",
     "As AI workloads balloon, researchers race to make data "
     "centers both renewable-powered and thermally efficient."),
    ("Why Some Countries Are Buying Up Farmland Overseas",
     "经济/政策", 2024, "12月",
     "Food-security concerns and shifting trade rules are "
     "driving a quiet land rush across Africa and Southeast Asia."),
]


# ---------------------------------------------------------------------------
# LLM call — straight to DeepSeek, no AIService detour so we don't pollute
# the live config.json with a one-off key.
# ---------------------------------------------------------------------------
def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text


def call_deepseek(prompt: str, system: str, key: str,
                   max_retries: int = 3) -> str | None:
    url = "https://api.deepseek.com/v1/chat/completions"
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.post(
                url,
                headers={"Authorization": f"Bearer {key}",
                          "Content-Type": "application/json"},
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.8,
                    "max_tokens": 2200,
                },
                timeout=60,
            )
            if r.status_code == 200:
                data = r.json()
                choices = data.get("choices") or []
                if choices:
                    return choices[0]["message"]["content"]
                return None
            # 5xx / 429 → retry
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 * attempt)
                continue
            print(f"  [deepseek] HTTP {r.status_code}: {r.text[:200]}")
            return None
        except requests.RequestException as e:
            print(f"  [deepseek] attempt {attempt} failed: {e}")
            time.sleep(2 * attempt)
    return None


def parse_article_response(raw: str) -> dict | None:
    """Pull {title, passage, questions[5]} out of a DeepSeek reply.
    Returns None on parse failure."""
    if not raw:
        return None
    body = _strip_code_fence(raw)
    try:
        data = json.loads(body)
    except Exception:
        match = re.search(r"\{[\s\S]*\}", body)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except Exception:
            return None
    if not data.get("passage") or not data.get("questions"):
        return None
    qs = data["questions"]
    if not isinstance(qs, list) or len(qs) < 4:
        return None
    # Take 5
    qs = qs[:5]
    # Validate each
    cleaned = []
    for q in qs:
        if not (q.get("q") and q.get("options") and q.get("answer")):
            return None
        opts = q["options"]
        if not isinstance(opts, list) or len(opts) < 4:
            return None
        cleaned.append({
            "q": str(q["q"]).strip(),
            "options": [str(o).strip() for o in opts[:4]],
            "answer": str(q["answer"]).strip().upper()[:1],
            "analysis": str(q.get("analysis", "")).strip(),
        })
    return {
        "title": str(data.get("title", "")).strip() or "(无标题)",
        "passage": str(data["passage"]).strip(),
        "questions": cleaned,
    }


def build_prompt(title: str, topic: str, level: str,
                  hint: str) -> str:
    """Craft a prompt that explicitly demands CET-4/6 exam style."""
    if level == "CET4":
        word_target = "280-360"
    else:
        word_target = "380-460"
    return (
        f"You are a Chinese college English exam writer. Produce one "
        f"original {level} reading comprehension passage and 5 "
        f"comprehension questions.\n\n"
        f"Topic hint: {topic}\n"
        f"Headline (translate to English): {title}\n"
        f"Conceptual brief: {hint}\n\n"
        f"Strict requirements:\n"
        f"  - 4 to 5 paragraphs, total {word_target} English words.\n"
        f"  - Argumentative / expository style (no dialogue, no lists).\n"
        f"  - Sentence complexity appropriate for {level}.\n"
        f"  - 5 questions: a mix of main idea, detail, inference, "
        f"and vocabulary-in-context. Each has 4 options A/B/C/D.\n"
        f"  - Exactly ONE option is correct; distractors are "
        f"plausible but wrong.\n"
        f"  - For each question, add 'analysis': 1-2 Chinese "
        f"sentences explaining why the correct answer is right.\n\n"
        f"Return STRICT JSON, no markdown fence, no commentary:\n"
        "{\n"
        '  "title": "English title of the passage",\n'
        '  "passage": "full English passage with paragraph breaks as \\n\\n",\n'
        '  "questions": [\n'
        '    {"q": "...", "options": ["A. ...", "B. ...", "C. ...", "D. ..."], "answer": "B", "analysis": "中文 1-2 句"}\n'
        '  ]  // exactly 5 entries\n'
        "}"
    )


def insert_article(level: str, year: int, session: str,
                    title: str, topic: str, data: dict) -> int:
    """Insert one article into reading table. Returns rowid."""
    questions_json = json.dumps(
        [{"q": q["q"], "options": q["options"]} for q in data["questions"]],
        ensure_ascii=False,
    )
    answers_text = " ".join(q["answer"] for q in data["questions"])
    analysis_lines = [
        f"Q{i+1}. {q['analysis']}" for i, q in enumerate(data["questions"])
        if q.get("analysis")
    ]
    full_analysis = "\n".join(analysis_lines) or "本篇为 AI 原创模拟题。"

    # Mark AI-original in the title so the user can't be misled
    display_title = f"[AI 原创] {title}"
    if session == "6月":
        session_label = f"{year} 6月 (AI 原创)"
    else:
        session_label = f"{year} 12月 (AI 原创)"

    with sqlite3.connect(str(DB_PATH)) as c:
        cur = c.execute(
            "INSERT INTO reading "
            "(level, year, session, passage_title, passage, questions, "
            " answers, analysis, topic_type, exam_type) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (level, year, session_label, display_title, data["passage"],
             questions_json, answers_text, full_analysis, topic, level),
        )
        c.commit()
        return cur.lastrowid


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--key", default=os.environ.get("DEEPSEEK_API_KEY"),
        help="DeepSeek API key (or set DEEPSEEK_API_KEY env var).",
    )
    parser.add_argument(
        "--level", choices=["CET4", "CET6", "both"], default="both",
    )
    args = parser.parse_args()
    if not args.key:
        print("ERROR: pass --key sk-... or set DEEPSEEK_API_KEY env var",
              file=sys.stderr)
        return 2

    # Wipe reading table
    with sqlite3.connect(str(DB_PATH)) as c:
        before = c.execute("SELECT COUNT(*) FROM reading").fetchone()[0]
        c.execute("DELETE FROM reading")
        c.commit()
        print(f"[seed_readings] wiped {before} existing reading rows")

    levels = (["CET4", "CET6"] if args.level == "both"
              else [args.level])
    topics_map = {"CET4": CET4_TOPICS, "CET6": CET6_TOPICS}
    system_prompt = (
        "你是一位经验丰富的中国大学英语四六级命题专家。"
        "请严格按照用户指定的 JSON 字段格式输出,不要写任何额外说明或 markdown。"
    )

    succeeded = failed = 0
    for level in levels:
        for title, topic, year, session, hint in topics_map[level]:
            print(f"\n[seed] {level} | {title}")
            prompt = build_prompt(title, topic, level, hint)
            raw = call_deepseek(prompt, system_prompt, args.key)
            if not raw:
                print(f"  [skip] no LLM response")
                failed += 1
                continue
            data = parse_article_response(raw)
            if not data:
                print(f"  [skip] parse failure (response first 200: "
                      f"{raw[:200]!r})")
                failed += 1
                continue
            wc = len(data["passage"].split())
            qc = len(data["questions"])
            if wc < 220 or qc < 4:
                print(f"  [skip] too short: {wc} words, {qc} questions")
                failed += 1
                continue
            try:
                rid = insert_article(level, year, session, title, topic, data)
                print(f"  [ok] rowid={rid} | {wc} words | {qc} questions")
                succeeded += 1
            except Exception as e:
                print(f"  [err] insert failed: {e}")
                failed += 1
            time.sleep(0.6)  # gentle rate-limit

    # Report
    with sqlite3.connect(str(DB_PATH)) as c:
        c.row_factory = sqlite3.Row
        total = c.execute("SELECT COUNT(*) FROM reading").fetchone()[0]
        per_level = {r["level"]: r["n"] for r in c.execute(
            "SELECT level, COUNT(*) AS n FROM reading GROUP BY level"
        )}
        avg_wc = {r["level"]: int(r["avg_w"]) for r in c.execute(
            "SELECT level, AVG(LENGTH(passage)) AS avg_w "
            "FROM reading GROUP BY level"
        )}

    print(f"\n[done] succeeded={succeeded}  failed={failed}")
    print(f"[done] reading total = {total}  per level = {per_level}")
    print(f"[done] avg passage chars = {avg_wc}")
    return 0 if succeeded == len(levels) * 5 else 1


if __name__ == "__main__":
    sys.exit(main())
