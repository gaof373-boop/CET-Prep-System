"""Synthetic source: generate practice material without network.

Used as a guaranteed fallback when no source can be reached. Output is
clearly tagged as ``synthetic`` and consists of high-quality template-
based material that is *comparable in structure* to CET exams without
copying any actual exam content.
"""

from __future__ import annotations

import json
import random
from typing import Iterator

from crawler.base import RawItem, log


# ---------- listening ----------
LISTENING_SCENARIOS = [
    ("校园/生活", [
        "library study", "cafeteria ordering", "club sign-up", "dorm check-in",
        "lost-and-found inquiry", "campus tour",
    ]),
    ("出行", [
        "booking a flight", "renting a car", "checking into a hotel",
        "buying a train ticket", "asking for directions", "airport security",
    ]),
    ("职场", [
        "job interview", "performance review", "team meeting", "client call",
        "salary negotiation", "project kickoff",
    ]),
]


def _listening_script(level: str, scenario: str) -> dict:
    speakers = ["W", "M"]
    s1, s2 = random.sample(speakers, 2)
    body = (
        f"{s1}: Hi, thanks for joining me today to talk about {scenario}.\n"
        f"{s2}: Of course. It's something I care a lot about.\n"
        f"{s1}: Could you start by telling me what first got you interested in it?\n"
        f"{s2}: Sure. A few years ago, I noticed that {scenario} was changing fast, "
        f"and I wanted to understand the bigger picture.\n"
        f"{s1}: Interesting. What do you think is the biggest challenge today?\n"
        f"{s2}: Honestly, it's balancing speed with quality. Everyone wants results "
        f"yesterday, but doing it right takes time.\n"
        f"{s1}: Any advice for someone just starting out?\n"
        f"{s2}: Be patient. Stay curious. And don't be afraid to ask for help — "
        f"the community around {scenario} is generous with newcomers."
    )
    if "library" in scenario or "cafeteria" in scenario or "campus" in scenario or "dorm" in scenario:
        topic_type = "校园/生活"
    elif "flight" in scenario or "hotel" in scenario or "train" in scenario or "airport" in scenario or "car" in scenario:
        topic_type = "出行"
    else:
        topic_type = "职场"
    return {
        "audio_script": body,
        "questions": json.dumps([
            {"q": "What is the conversation mainly about?",
             "options": [f"A. {scenario}", "B. Weather", "C. Food", "D. A different topic"]},
            {"q": "What does the second speaker say is the biggest challenge?",
             "options": ["A. Time management", "B. Speed vs. quality", "C. Lack of money", "D. Health"]},
            {"q": "What is the second speaker's advice to beginners?",
             "options": ["A. Give up early", "B. Be patient and curious", "C. Work alone", "D. Spend more money"]},
        ], ensure_ascii=False),
        "answers": "1. A  2. B  3. B",
        "analysis": "对话围绕某一场景展开,关键词在第二、四、六轮。注意:不要被无关信息误导。",
        "section": "短对话",
        "topic_type": topic_type,
    }


def fetch(scraper) -> Iterator[RawItem]:  # noqa: ARG001
    log.info("  synthetic: generating listening + writing items…")
    for level in ("CET4", "CET6"):
        for _, group in LISTENING_SCENARIOS:
            for scenario in group[:2]:  # 2 per group per level = 6 per level
                d = _listening_script(level, scenario)
                yield RawItem(
                    source="synthetic", section="listening", level=level,
                    payload={
                        "section": d["section"],
                        "audio_script": d["audio_script"],
                        "questions": d["questions"],
                        "answers": d["answers"],
                        "analysis": d["analysis"],
                        "topic_type": d["topic_type"],
                    },
                )
    # writing prompts
    writing_prompts = [
        ("CET4", "A letter to your friend describing your favorite festival.",
         "应用文 / 节日介绍"),
        ("CET4", "An email applying for a student volunteer position at an international conference.",
         "应用文 / 申请信"),
        ("CET4", "A short essay on the impact of smartphones on study habits (around 120 words).",
         "议论文 / 科技与学习"),
        ("CET6", "A bar chart shows graduate destinations in 2024: 35% further study, 60% employed, 5% entrepreneur. Discuss the reasons and your view.",
         "图表作文 / 就业"),
        ("CET6", "Some say 'failure is the mother of success'. Do you agree? Give reasons and examples.",
         "议论文 / 哲理"),
        ("CET6", "Should companies allow employees to work from home permanently? Write an essay of about 150 words.",
         "议论文 / 职场"),
    ]
    for level, prompt, category in writing_prompts:
        yield RawItem(
            source="synthetic", section="writing", level=level,
            payload={
                "topic": prompt.split(".")[0] if "." in prompt else prompt,
                "requirements": prompt,
                "sample_essay": (
                    f"[Synthetic essay]\n\nIn recent years, this topic has drawn increasing attention. "
                    f"On the one hand, supporters point out the benefits; on the other, critics "
                    f"highlight the risks. From my perspective, the key is balance — embracing "
                    f"the opportunity while staying mindful of the limits. To conclude, I believe "
                    f"thoughtful engagement produces the best outcomes for individuals and society."
                ),
                "key_phrases": "increasing attention, on the one hand, balance, mindful",
                "category": category,
            },
        )
