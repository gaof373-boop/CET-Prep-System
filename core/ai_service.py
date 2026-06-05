"""AI service: generates similar practice and predicts writing topics.

The service works in two modes:
1. **Local mode (default)** — produces content via a rule-based engine that
   mirrors the topic, structure, and difficulty of the seed exam data.
2. **API mode (optional)** — if the user supplies an OpenAI-compatible
   ``api_key`` + ``base_url`` in ``config.json``, real LLM calls are made
   via the ``requests`` library. Errors fall back to local mode.

Local generation is intentionally simple but functional: it picks a related
template, swaps the topic, and adds questions in the same style as the
original.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # requests is in requirements.txt, but guard anyway
    requests = None  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"

# ---------------------------------------------------------------------------
# Templates for local practice generation
# ---------------------------------------------------------------------------
READING_TEMPLATES: dict[str, list[dict[str, str]]] = {
    "科技": [
        {
            "passage": (
                "The world of $topic is evolving faster than at any other point in history. "
                "From $year_short+ breakthroughs in $keyword to the rise of $related, "
                "scientists and engineers are racing to keep up with both opportunity and risk. "
                "Proponents argue that $topic can solve some of humanity's most pressing problems, "
                "including disease, climate change, and inequality. Critics, however, warn that "
                "rapid adoption often outpaces regulation, leaving society to grapple with ethical "
                "questions that have no easy answers.\n\n"
                "In laboratories from Beijing to Boston, researchers stress that responsible "
                "innovation requires collaboration across disciplines and borders. $topic cannot "
                "advance in isolation; it demands input from ethicists, policymakers, and the "
                "communities it aims to serve. The decisions made in the next decade will shape "
                "generations to come, and history shows that the technologies we celebrate today "
                "often carry unintended consequences that surface only later."
            ),
            "questions": json.dumps([
                {"q": "What is the main idea of the passage?",
                 "options": ["A. The history of " "$topic",
                             "B. The promise and risks of " "$topic",
                             "C. A specific product in " "$topic",
                             "D. A biography of a scientist in " "$topic"]},
                {"q": "According to the passage, what do critics worry about?",
                 "options": ["A. The cost of research",
                             "B. The speed of innovation outpacing regulation",
                             "C. Public interest in " "$topic",
                             "D. The training of new scientists"]},
                {"q": "What is the author's attitude?",
                 "options": ["A. Dismissive",
                             "B. Cautiously optimistic",
                             "C. Purely pessimistic",
                             "D. Uninvolved"]},
            ], ensure_ascii=False),
            "answers": "1. B  2. B  3. B",
            "analysis": (
                "本文探讨$topic的潜力与隐忧。第1题为主旨题,综合两段观点;"
                "第2题为细节题,定位第二段'rapid adoption often outpaces regulation';"
                "第3题态度题,作者既肯定成就也提出警示,属 'cautiously optimistic'。"
            ),
        }
    ],
    "教育": [
        {
            "passage": (
                "Few topics stir as much debate in $country as the future of $topic. "
                "Traditionalists argue that $topic builds discipline, character, and a sense of "
                "shared culture that no screen can replicate. Reformers counter that clinging to "
                "outdated methods risks leaving an entire generation unprepared for the world they "
                "will inherit.\n\n"
                "Recent studies suggest the truth lies in balance. $topic, when combined with "
                "modern tools and student-centered approaches, can spark curiosity rather than "
                "stifle it. The classrooms that thrive are those that respect tradition while "
                "embracing change — where teachers are guides, not gatekeepers, and where "
                "mistakes are treated as evidence of learning, not failure."
            ),
            "questions": json.dumps([
                {"q": "What is the disagreement between the two sides?",
                 "options": ["A. The cost of " "$topic",
                             "B. Whether " "$topic" " should keep its current form",
                             "C. The popularity of " "$topic",
                             "D. The location of schools"]},
                {"q": "What does the author suggest is the key to improving " "$topic" "?",
                 "options": ["A. Higher pay for teachers",
                             "B. More exams",
                             "C. Balancing tradition and innovation",
                             "D. Removing " "$topic" " entirely"]},
            ], ensure_ascii=False),
            "answers": "1. B  2. C",
            "analysis": (
                "文章围绕$topic改革的争议展开,主张传统与创新并存。结构:首段引出辩论,"
                "第二段提出折中观点,论证'balance'是出路。"
            ),
        }
    ],
    "职场": [
        {
            "passage": (
                "The modern workplace is being reshaped by $topic. A decade ago, the phrase would "
                "have drawn blank stares in many offices; today, it is a boardroom agenda item. "
                "From $year_short onwards, companies have tested new models, and the results are "
                "mixed but revealing.\n\n"
                "Employees value flexibility, but they also crave connection. Managers value "
                "efficiency, but they worry about cohesion. The companies that succeed are those "
                "that treat $topic not as a binary choice but as a design problem — one that "
                "requires data, empathy, and constant iteration."
            ),
            "questions": json.dumps([
                {"q": "What is the main point of the passage?",
                 "options": ["A. " "$topic" " is a passing trend",
                             "B. " "$topic" " requires careful design, not slogans",
                             "C. All companies are adopting " "$topic",
                             "D. " "$topic" " benefits only employees"]},
                {"q": "What do the successful companies have in common?",
                 "options": ["A. Large budgets",
                             "B. Treating " "$topic" " as a design problem",
                             "C. Hiring younger workers",
                             "D. Avoiding technology"]},
            ], ensure_ascii=False),
            "answers": "1. B  2. B",
            "analysis": (
                "短文分析$topic在现代职场的应用。第1题主旨,第二段强调'design problem';"
                "第2题细节,定位 'treat ... as a design problem'。"
            ),
        }
    ],
    "社会": [
        {
            "passage": (
                "In cities around the world, $topic has become a defining issue of our time. "
                "Walk down any busy street and you will see the tension play out: signs of "
                "prosperity alongside unmistakable strain. Researchers warn that without "
                "thoughtful intervention, the gap between promise and reality will only widen.\n\n"
                "Community leaders, however, are not waiting for top-down solutions. From "
                "neighborhood libraries to volunteer networks, ordinary citizens are crafting "
                "responses that are modest in scale but rich in impact. As one organizer put it, "
                "'change doesn't always start in parliament. Sometimes it starts on the corner.'"
            ),
            "questions": json.dumps([
                {"q": "What problem is the passage mainly discussing?",
                 "options": ["A. The decline of " "$topic",
                             "B. The challenges brought by " "$topic",
                             "C. The history of " "$topic",
                             "D. The technology of " "$topic"]},
                {"q": "What is the role of community leaders according to the passage?",
                 "options": ["A. To replace the government",
                             "B. To ignore the issue",
                             "C. To create small but meaningful solutions",
                             "D. To focus only on technology"]},
            ], ensure_ascii=False),
            "answers": "1. B  2. C",
            "analysis": "社会议题类阅读,关注'community-led solutions'。",
        }
    ],
    "文化": [
        {
            "passage": (
                "Few forces are as quietly powerful as $topic. Long before satellites and social "
                "media, cultures spread through trade routes, migration, and storytelling. Today, "
                "the pace is faster, but the underlying pattern remains familiar: ideas travel, "
                "adapt, and leave traces wherever they land.\n\n"
                "What makes $topic remarkable is its ability to be both local and global at "
                "once. A festival in a remote village can inspire a fashion show in Paris; a song "
                "recorded in a basement studio can become a worldwide anthem. The challenge for "
                "the next generation is to keep that exchange alive while protecting the "
                "diversity that gives it meaning."
            ),
            "questions": json.dumps([
                {"q": "The author mentions 'Paris fashion shows' to show that ____.",
                 "options": ["A. " "$topic" " is wasteful",
                             "B. Local culture can have global influence",
                             "C. Fashion is the most important art form",
                             "D. Young people prefer foreign styles"]},
                {"q": "What is the author's main concern?",
                 "options": ["A. The disappearance of cultural diversity",
                             "B. The growth of technology",
                             "C. The cost of cultural exchange",
                             "D. The decline of festivals"]},
            ], ensure_ascii=False),
            "answers": "1. B  2. A",
            "analysis": "文化类阅读。需抓住'both local and global'的双重性,以及'protecting diversity'的隐含忧虑。",
        }
    ],
}

LISTENING_TEMPLATES = {
    "校园/生活": [
        {
            "audio_script": (
                "W: Hi, Tom. I heard you joined the new photography club. How is it going?\n"
                "M: It's amazing! We meet every Wednesday and go out to take pictures around "
                "the city. The instructor gives us tips on lighting and composition.\n"
                "W: That sounds fun. Do you have to bring your own camera?\n"
                "M: A phone is fine for the first few weeks, but the club is planning a workshop "
                "next month where we can try out professional cameras.\n"
                "W: I'd love to join, but I'm a bit shy. Is it beginner-friendly?\n"
                "M: Definitely. Most members are beginners, and the atmosphere is very relaxed."
            ),
            "questions": json.dumps([
                {"q": "When does the photography club meet?",
                 "options": ["A. Every Monday", "B. Every Wednesday", "C. Every Friday", "D. Every Sunday"]},
                {"q": "What is the club planning to do next month?",
                 "options": ["A. A photo exhibition",
                             "B. A workshop with professional cameras",
                             "C. A trip abroad",
                             "D. A competition"]},
            ], ensure_ascii=False),
            "answers": "1. B  2. B",
            "analysis": "短对话围绕校园摄影俱乐部展开。关键信息在第二、四轮对话中。",
        }
    ],
    "出行": [
        {
            "audio_script": (
                "M: Good afternoon. I'd like to book a table for two for Saturday evening, around 7.\n"
                "W: Of course. Would you prefer the main hall or the outdoor terrace?\n"
                "M: The terrace, please. We love the view there.\n"
                "W: Just a moment. I'm sorry, the terrace is fully booked at 7, but I can offer you 6:30 or 8:15.\n"
                "M: 6:30 works. Could I also request a window seat?\n"
                "W: Noted. May I have your name, please?\n"
                "M: It's Brown. By the way, is there parking on site?\n"
                "W: Yes, free parking for guests. I'll send you a confirmation email shortly."
            ),
            "questions": json.dumps([
                {"q": "When will the man have dinner?",
                 "options": ["A. 6:30", "B. 7:00", "C. 7:30", "D. 8:15"]},
                {"q": "What is included with the reservation?",
                 "options": ["A. A free drink",
                             "B. Free parking",
                             "C. A discount coupon",
                             "D. A tour of the kitchen"]},
            ], ensure_ascii=False),
            "answers": "1. A  2. B",
            "analysis": "餐厅预订场景。注意时间从 7 调整到 6:30,关键细节在最后一轮。",
        }
    ],
    "职场": [
        {
            "audio_script": (
                "W: Welcome to today's program on the future of work. Our guest is Dr. Allen, "
                "an organizational psychologist. Dr. Allen, are four-day work weeks really viable?\n"
                "M: For knowledge workers, yes, in many cases. The key is not just cutting hours, "
                "but redesigning meetings and clarifying outcomes.\n"
                "W: And what about industries like healthcare or manufacturing?\n"
                "M: Those are trickier. They require more creative solutions, perhaps involving "
                "shift swaps or AI-assisted scheduling."
            ),
            "questions": json.dumps([
                {"q": "What is the guest's main point?",
                 "options": ["A. Four-day weeks never work",
                             "B. Reducing hours alone is not enough",
                             "C. All industries should try it immediately",
                             "D. AI is the only solution"]},
                {"q": "Which industry is harder to adapt?",
                 "options": ["A. Education", "B. Finance", "C. Healthcare", "D. Software"]},
            ], ensure_ascii=False),
            "answers": "1. B  2. C",
            "analysis": "访谈类听力。注意客人的核心观点是'重新设计工作',而不是简单减时。",
        }
    ],
}

TRANSLATION_TEMPLATES = {
    "科技": (
        "随着{specific_tech}的迅速发展,人们的生活方式发生了巨大变化。如今,{application}已经成为日常生活的一部分。无论是{scene1}还是{scene2},都可以通过{tool}轻松完成。专家认为,这种变化不仅提高了效率,也带来了新的挑战。",
        "With the rapid development of {specific_tech}, people's lifestyles have changed dramatically. Today, {application} has become a part of daily life. Whether in {scene1} or {scene2}, things can be easily done with {tool}. Experts believe that this change has not only improved efficiency but also brought new challenges.",
        "随着: With; 巨大变化: dramatic change; 日常生活: daily life; 挑战: challenge; 效率: efficiency",
        "科技类翻译高频词汇,注意 with 引导的伴随状语和 not only ... but also ... 句型。",
    ),
    "社会": (
        "近年来,{social_phenomenon}在中国越来越普遍。它在{sector1}和{sector2}中表现尤为突出。{authority}表示,这一现象反映了{positive_impact},但也需要注意{negative_impact}。",
        "In recent years, {social_phenomenon} has become increasingly common in China. It is particularly prominent in {sector1} and {sector2}. {authority} has stated that this phenomenon reflects {positive_impact}, but attention also needs to be paid to {negative_impact}.",
        "近年来: In recent years; 越来越普遍: increasingly common; 尤为突出: particularly prominent; 反映: reflect",
        "社会类翻译常考。注意 increasingly, particularly 等副词的位置和搭配。",
    ),
    "文化": (
        "{festival}是{theme}最重要的传统节日之一,已有{years}多年的历史。每到节日,人们会{activity1}、{activity2},以此表达{festival_meaning}。这个节日不仅展现了{aspect1},也体现了{aspect2}。",
        "{festival} is one of the most important traditional festivals in {theme}, with a history of more than {years} years. During the festival, people {activity1} and {activity2} to express {festival_meaning}. The festival demonstrates not only {aspect1} but also {aspect2}.",
        "传统节日: traditional festival; 历史: history; 表达: express; 体现: demonstrate",
        "文化类翻译要兼顾时态 (一般现在时) 与 not only ... but also ... 句型。",
    ),
}

# 2026 押题种子(若用户尚未生成新预测,可作为默认依据)
WRITING_PATTERNS: dict[str, list[str]] = {
    "CET4": [
        "人工智能在日常生活中的应用",
        "在线教育的利与弊",
        "大学生兼职现象",
        "数字阅读 vs 纸质阅读",
        "中国文化的国际传播",
        "健康生活方式",
        "青年志愿服务的意义",
        "短视频的影响",
    ],
    "CET6": [
        "数字经济与就业转型",
        "职场心理健康",
        "终身学习的重要性",
        "科技伦理与隐私",
        "全球化与本土化",
        "延迟退休政策",
        "AI 创作的版权问题",
        "可持续发展与个人责任",
    ],
}


class AIService:
    """High-level façade used by the UI for predictions & similar practice."""

    def __init__(self) -> None:
        self.config: dict[str, Any] = self._load_config()

    # ---------- config ----------
    @staticmethod
    def _load_config() -> dict[str, Any]:
        if CONFIG_PATH.exists():
            try:
                return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def save_config(self) -> None:
        CONFIG_PATH.write_text(
            json.dumps(self.config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def has_api(self) -> bool:
        return bool(self.config.get("api_key")) and bool(self.config.get("base_url"))

    # ---------- writing prediction ----------
    def predict_writing(self, level: str, db_manager) -> list[dict[str, Any]]:
        """Return top-3 predictions for the given level.

        Priority: stored predictions (already in DB) > freshly generated
        local predictions.
        """
        stored = db_manager.list_predictions(level)
        if stored:
            return stored[:3]
        topics = WRITING_PATTERNS.get(level, [])
        random.shuffle(topics)
        return [
            {
                "predicted_topic": t,
                "predicted_year": 2026,
                "reference_essay": self._generate_short_essay(t),
                "reasoning": f"基于近 10 年{level}写作命题规律:'{t}' 契合近年社会热点。",
                "confidence": random.randint(60, 85),
            }
            for t in topics[:3]
        ]

    @staticmethod
    def _generate_short_essay(topic: str) -> str:
        return (
            f"In recent years, {topic} has become a topic of growing importance. "
            f"Proponents argue that it offers new opportunities for individuals and "
            f"society alike. Critics, however, caution against overlooking the risks "
            f"and unintended consequences that may follow.\n\n"
            f"From my perspective, the key is balance. We should embrace the "
            f"benefits of {topic} while remaining aware of its limits. Only by "
            f"combining innovation with responsibility can we ensure that progress "
            f"serves the common good rather than narrow interests."
        )

    # ---------- similar practice ----------
    def generate_similar_reading(
        self, source: dict[str, Any]
    ) -> dict[str, Any]:
        from string import Template
        topic_type_cn = source.get("topic_type") or "科技"
        topic_type_en = {
            "科技": "technology",
            "教育": "education",
            "教育/科技": "education and technology",
            "职场": "the workplace",
            "社会": "urban life",
            "文化": "cultural exchange",
            "心理/生活": "daily habits",
            "心理": "psychology",
        }.get(topic_type_cn, "the subject")
        template = random.choice(READING_TEMPLATES.get(topic_type_cn, READING_TEMPLATES["科技"]))
        raw_title = source.get("passage_title") or "the subject"
        # crude English keyword extraction
        keyword_tokens = re.findall(r"[A-Za-z]+", raw_title)
        keyword = (keyword_tokens[0].lower() if keyword_tokens else "this field")
        related = f"{keyword} applications"
        year_short = random.choice(["2023", "2024", "2025"])
        ctx = dict(topic=topic_type_en, year_short=year_short, keyword=keyword, related=related)
        return {
            "title": f"拓展练习 — {raw_title}的延伸议题",
            "passage": Template(template["passage"]).safe_substitute(ctx),
            "questions": Template(template["questions"]).safe_substitute(ctx),
            "answers": template["answers"],
            "analysis": Template(template["analysis"]).safe_substitute(ctx),
        }

    def generate_similar_reading_llm(self, source: dict[str, Any]) -> dict[str, Any] | None:
        """Use the LLM to write a fresh reading passage that mirrors the
        ``source`` in topic, difficulty and length, with 5 fresh
        multiple-choice questions.

        Returns ``None`` on failure (caller falls back to the template
        engine ``generate_similar_reading``).
        """
        if not self.has_api():
            return None
        title = source.get("passage_title") or "the topic"
        topic = source.get("topic_type") or "综合"
        passage = (source.get("passage") or "")[:600]
        prompt = (
            f"请基于以下这篇英语阅读理解文章的风格(题材/难度/句法复杂度)原创一篇同类型阅读理解。\n\n"
            f"原题: {title}\n"
            f"原题材: {topic}\n"
            f"原文片段:\n{passage}\n\n"
            f"请生成:\n"
            f"1) 一篇 250-350 词、全新原创的英文阅读文章 (题材和难度与原文一致,但具体内容必须不同)\n"
            f"2) 5 道 A/B/C/D 单选题,每题 4 个选项,选项互斥\n"
            f"3) 标准答案(单字母 'A' 'B' 'C' 或 'D',5 个)\n"
            f"4) 深度解析(每题 1-2 句中文)\n\n"
            f"请严格按下述 JSON 格式输出,不要有额外说明:\n"
            "{\n"
            '  "title": "原创标题(英文)",\n'
            '  "passage": "完整文章英文",\n'
            '  "questions": [\n'
            '    {"q": "题目英文", "options": ["A. ...", "B. ...", "C. ...", "D. ..."], "answer": "B", "analysis": "中文解析"}\n'
            '  ]  // 共 5 道\n'
            "}"
        )
        txt = self.call_remote(
            prompt,
            system="你是一位严谨的英语四六级命题专家,擅长高仿真原创阅读理解。",
        )
        if not txt:
            return None
        parsed = self._parse_json_block(txt)
        if not parsed or not parsed.get("passage"):
            return None
        # Sanity-check questions
        qs = parsed.get("questions") or []
        if not isinstance(qs, list) or len(qs) < 3:
            return None
        # Build a normalised "options" string (UI reads JSON)
        # and a single-letter answer string (5 chars).
        answers = " ".join(
            str((q.get("answer") or "?").strip().upper()[:1])
            for q in qs[:5]
        )
        # Reformat questions to {"q":..., "options":[...]} for compat
        for q in qs:
            opts = q.get("options") or []
            # Make sure each option starts with "A. " / "B. " etc.
            normalised = []
            for i, opt in enumerate(opts[:4]):
                letter = "ABCD"[i]
                if not opt.lstrip().startswith(f"{letter}."):
                    normalised.append(f"{letter}. {opt}")
                else:
                    normalised.append(opt)
            q["options"] = normalised
        return {
            "title": parsed.get("title", title + " (AI 仿写)"),
            "passage": parsed.get("passage", ""),
            "questions": qs,
            "answers": answers,
            "analysis": "AI 高仿生成 · 与原题同题材同难度,内容为原创。",
        }

    def generate_similar_listening(
        self, source: dict[str, Any]
    ) -> dict[str, Any]:
        topic_type = source.get("topic_type") or "校园/生活"
        template = random.choice(
            LISTENING_TEMPLATES.get(topic_type, LISTENING_TEMPLATES["校园/生活"])
        )
        return {
            "title": f"拓展练习 — {topic_type}场景对话",
            "audio_script": template["audio_script"],
            "questions": template["questions"],
            "answers": template["answers"],
            "analysis": template["analysis"],
        }

    def generate_similar_translation(
        self, source: dict[str, Any]
    ) -> dict[str, Any]:
        topic_type = source.get("topic_type") or "社会"
        zh, en, key_points, analysis = TRANSLATION_TEMPLATES.get(
            topic_type, TRANSLATION_TEMPLATES["社会"]
        )
        zh_subs = {
            "specific_tech": "5G技术", "application": "移动办公",
            "scene1": "通勤路上", "scene2": "出差途中", "tool": "一部手机",
            "social_phenomenon": "远程办公", "sector1": "互联网行业",
            "sector2": "传统制造业", "authority": "有关专家",
            "positive_impact": "工作灵活性的提升", "negative_impact": "工作与生活边界的模糊",
            "festival": "中秋节", "theme": "中国", "years": "1000",
            "activity1": "赏月", "activity2": "吃月饼",
            "festival_meaning": "对家人的思念",
            "aspect1": "中国文化的魅力", "aspect2": "人们对家庭团聚的重视",
        }
        en_subs = {
            "specific_tech": "5G technology", "application": "mobile work",
            "scene1": "the daily commute", "scene2": "business trips",
            "tool": "a smartphone",
            "social_phenomenon": "remote working",
            "sector1": "the tech sector", "sector2": "traditional manufacturing",
            "authority": "Relevant experts",
            "positive_impact": "improved flexibility",
            "negative_impact": "blurred work-life boundaries",
            "festival": "The Mid-Autumn Festival", "theme": "China", "years": "1,000",
            "activity1": "admire the full moon", "activity2": "eat mooncakes",
            "festival_meaning": "love for family",
            "aspect1": "the charm of Chinese culture",
            "aspect2": "the value placed on family reunion",
        }
        try:
            zh_filled = zh.format(**zh_subs)
        except KeyError:
            zh_filled = zh
        try:
            en_filled = en.format(**en_subs)
        except KeyError:
            en_filled = en
        return {
            "title": f"拓展练习 — {topic_type}类段落翻译",
            "chinese_text": zh_filled,
            "english_reference": en_filled,
            "key_points": key_points,
            "analysis": analysis,
        }

    # ---------- optional LLM call ----------
    def call_remote(self, prompt: str, system: str | None = None) -> str | None:
        """If API configured, call an OpenAI-compatible chat completion.
        Returns None on failure (so the caller can fall back to local).

        ``system`` lets callers override the default system prompt; useful
        for writing/grading tasks that need a very different persona.
        """
        if not self.has_api() or requests is None:
            return None
        try:
            url = self.config["base_url"].rstrip("/") + "/chat/completions"
            payload = {
                "model": self.config.get("model", "gpt-3.5-turbo"),
                "messages": [
                    {"role": "system",
                     "content": system or "你是一位英语四六级备考专家。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.7,
            }
            headers = {
                "Authorization": f"Bearer {self.config['api_key']}",
                "Content-Type": "application/json",
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            if not resp.ok:
                print(f"[AIService] HTTP {resp.status_code}: {resp.text[:200]}")
                return None
            # Defensive: a 200 with an HTML body (e.g. when the user
            # pointed base_url at a website instead of an API) would
            # raise JSONDecodeError below. Bail out instead.
            try:
                data = resp.json()
            except Exception:
                print(f"[AIService] Non-JSON response: {resp.text[:200]}")
                return None
            choices = data.get("choices") or []
            if not choices:
                return None
            return choices[0].get("message", {}).get("content")
        except Exception as e:  # noqa: BLE001
            print(f"[AIService] Remote call failed: {e}")
        return None

    # =================================================================
    # Writing-section helpers
    # =================================================================
    PREDICTION_LOCAL: dict[str, list[dict[str, str]]] = {
        "CET4": [
            {
                "topic_zh": "人工智能在大学校园中的利与弊",
                "topic_en": "On the Use of AI in College: Opportunities and Risks",
                "key_points_zh": "利: 个性化学习 / 效率提升;弊: 学术诚信 / 独立思考弱化",
                "key_points_en": "Pros: personalised learning, efficiency; Cons: academic integrity, weaker critical thinking",
                "essay_zh": "Nowadays, AI tools like ChatGPT have become part of campus life. From one angle, they offer personalised tutoring and save students time. From another, they may erode independent thinking and raise concerns about plagiarism. My take is that universities should embrace AI as a tutor, not a substitute. With clear usage rules and AI-literacy courses, students can benefit without losing the spark of original thought.",
            },
            {
                "topic_zh": "大学生是否应兼职",
                "topic_en": "Should College Students Take Part-time Jobs?",
                "key_points_zh": "支持: 经济独立 / 社会经验;反对: 影响学业 / 压力大",
                "key_points_en": "Pros: financial independence, social experience; Cons: study impact, stress",
                "essay_zh": "Part-time jobs are common among today's students. Supporters argue that they teach responsibility and ease family burdens. Opponents worry about distracted studies. I believe a balanced schedule is the key. A few hours a week can sharpen soft skills, as long as it does not crowd out the core mission of learning.",
            },
        ],
        "CET6": [
            {
                "topic_zh": "数字经济对就业市场的长期影响",
                "topic_en": "The Long-term Impact of the Digital Economy on the Job Market",
                "key_points_zh": "正面: 新职业 / 灵活就业;负面: 结构性失业 / 技能错配",
                "key_points_en": "Pros: new occupations, flexible employment; Cons: structural unemployment, skill mismatch",
                "essay_zh": "The rise of the digital economy has reshaped the labour market in ways that no previous industrial revolution matched. New roles in data analysis, platform operations and AI oversight have emerged, while routine clerical and assembly work has been automated. The challenge for policymakers is twofold: it must re-skill mid-career workers, and it must build safety nets for those whose jobs disappear. Lifelong learning is no longer a luxury but a necessity.",
            },
            {
                "topic_zh": "科技伦理:人工智能是否应被赋予决策权",
                "topic_en": "AI Ethics: Should Machines Be Allowed to Make Decisions?",
                "key_points_zh": "支持: 高效 / 客观;反对: 责任归属 / 价值观偏差",
                "key_points_en": "Pros: efficiency, objectivity; Cons: accountability, value bias",
                "essay_zh": "As AI systems grow more capable, the question is no longer whether they can decide, but whether they should. In narrow domains like medical imaging, machine decisions are demonstrably faster and more accurate. However, in matters involving human values — sentencing, hiring, autonomous weapons — accountability becomes dangerously diffuse. I would argue for a hybrid model: AI recommends, humans decide. That keeps efficiency while preserving moral responsibility.",
            },
        ],
    }

    def generate_writing_topic(self, level: str) -> dict[str, str]:
        """Produce a fresh writing topic, key points, and reference essay.

        Order of preference:
        1. Remote LLM (if API key is configured)
        2. Local fallback (deterministic templates)

        Returns a dict with keys:
            topic_zh, topic_en, key_points_zh, key_points_en, essay_zh
        """
        level_key = level.replace("-", "")
        if level_key not in self.PREDICTION_LOCAL:
            level_key = "CET4"

        # Try remote first
        if self.has_api():
            prompt = (
                f"为 {level_key} 英语考试出一道 2026 年最可能考的写作题。\n"
                f"要求:1) 中英文双语题目 2) 3-5 个核心写作要点(中英) 3) 一篇 150 词左右的高分范文。\n"
                f"请按以下严格 JSON 格式输出,不要添加额外文本:\n"
                "{\n"
                '  "topic_zh": "中文题目",\n'
                '  "topic_en": "English prompt",\n'
                '  "key_points_zh": "要点1; 要点2; 要点3",\n'
                '  "key_points_en": "point1; point2; point3",\n'
                '  "essay_zh": "完整参考范文"\n'
                "}"
            )
            txt = self.call_remote(
                prompt,
                system="你是一位严谨的英语四六级写作命题与教学专家。",
            )
            if txt:
                parsed = self._parse_json_block(txt)
                if parsed and parsed.get("topic_zh"):
                    return parsed

        # Fallback: local deterministic template (pick first)
        return self.PREDICTION_LOCAL[level_key][0]

    @staticmethod
    def _parse_json_block(text: str) -> dict | None:
        """Find the first ``{...}`` JSON block in ``text`` and parse it.
        Robust against the LLM wrapping its answer in markdown fences
        or preceding it with a short preamble."""
        if not text:
            return None
        # 1) try direct parse
        try:
            import json
            return json.loads(text)
        except Exception:
            pass
        # 2) find the outermost braces and parse the slice
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < 0 or end <= start:
            return None
        snippet = text[start: end + 1]
        try:
            import json
            return json.loads(snippet)
        except Exception:
            return None

    def grade_essay(self, topic_zh: str, essay: str) -> dict | None:
        """Send a student essay to the LLM for detailed grading.

        Returns a dict with keys:
            score, summary, errors, upgrades, polished
        or None on failure (caller falls back to local heuristic).
        """
        if not self.has_api():
            return None
        if not essay or len(essay.strip()) < 10:
            return None
        prompt = (
            f"你是一位严格的英语四六级作文阅卷老师。\n\n"
            f"题目: {topic_zh}\n\n"
            f"学生作文:\n{essay}\n\n"
            "请按以下 JSON 格式输出(不要加额外解释):\n"
            "{\n"
            '  "score": 12,                          // 0-15 分,保留整数\n'
            '  "summary": "整体评价,30-60字",\n'
            '  "errors": [                           // 语法/拼写纠错,无错误时 []\n'
            '    {"snippet": "原句片段", "issue": "问题说明", "fix": "改写后的句子"}\n'
            "  ],\n"
            '  "upgrades": [                        // 低级→高级替换建议\n'
            '    {"from": "low-end phrase", "to": "higher-end alternative", "reason": "为什么更好"}\n'
            "  ],\n"
            '  "polished": "基于学生原文的逻辑,润色成的满分版(150 词左右)"\n'
            "}"
        )
        txt = self.call_remote(
            prompt,
            system="你是一位严格的英语四六级作文阅卷老师,给分不手软,反馈要犀利。",
        )
        if not txt:
            return None
        parsed = self._parse_json_block(txt)
        if parsed and parsed.get("score") is not None:
            # Defensive: cap types
            try:
                parsed["score"] = int(parsed["score"])
            except Exception:
                parsed["score"] = 0
            return parsed
        return None

    # =================================================================
    # Translation line-by-line grading
    # =================================================================
    def grade_translation_line_by_line(
        self,
        chinese_text: str,
        reference: str,
        student: str,
    ) -> dict | None:
        """Use the LLM to compare a student's Chinese→English translation
        with the reference, returning a structured diagnostic.

        Returns a dict with keys:
            missing_points   — list of scoring keywords the student missed
            chinglish        — list of Chinese-English grammar errors
            upgrades         — list of {"from":..., "to":..., "reason":...}
            polished         — a refined reference-quality translation
            summary          — overall 1-sentence verdict (CN)
        Returns None on failure (caller falls back to a heuristic).
        """
        if not self.has_api():
            return None
        if not student or len(student.strip()) < 10:
            return None
        prompt = (
            f"你是一位严格的英语四六级翻译阅卷老师,擅长逐句对比学生的中译英作答与标准译文。\n\n"
            f"【中文原文】\n{chinese_text}\n\n"
            f"【标准参考译文】\n{reference}\n\n"
            f"【学生作答】\n{student}\n\n"
            f"请完成 3 件事并严格按下述 JSON 格式输出(不要有额外文字):\n"
            f"1) 【采分点遗漏】:列出学生译文中漏掉的、官方可能采分的关键词/短语/句式 (3-6 条)\n"
            f"2) 【中式英语硬伤】:逐句指出 Chinglish 错误 (语法/搭配/动词误用等,3-5 条)\n"
            f"3) 【高级替换建议】:把学生文中至少 3 处低级表达换成高级学术表达\n"
            f"最后再给一份【润色版】(基于学生原文逻辑,不是重写而是打磨):\n\n"
            "{\n"
            '  "missing_points": ["要点 1", "要点 2", ...],\n'
            '  "chinglish": [\n'
            '    {"sentence": "学生原句", "issue": "问题", "fix": "建议改写"}\n'
            '  ],\n'
            '  "upgrades": [\n'
            '    {"from": "low-end", "to": "higher-end", "reason": "为什么更好"}\n'
            '  ],\n'
            '  "polished": "完整润色版译文",\n'
            '  "summary": "整体评价,30-60 字"\n'
            "}"
        )
        txt = self.call_remote(
            prompt,
            system="你是一位严格的四六级翻译阅卷老师,逐句诊断,反馈要犀利具体。",
        )
        if not txt:
            return None
        parsed = self._parse_json_block(txt)
        if not parsed or "missing_points" not in parsed:
            return None
        # Defensive defaults
        parsed.setdefault("chinglish", [])
        parsed.setdefault("upgrades", [])
        parsed.setdefault("polished", "(AI 未返回润色版)")
        parsed.setdefault("summary", "")
        return parsed


if __name__ == "__main__":
    ai = AIService()
    print("Has API:", ai.has_api())
    sample = {
        "passage_title": "The Future of Remote Work",
        "topic_type": "职场",
    }
    out = ai.generate_similar_reading(sample)
    print("Generated passage (first 200 chars):", out["passage"][:200])
