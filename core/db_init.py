"""SQLite schema and seed data for the CET prep system.

Run this file directly to (re)initialize the database:
    python -m core.db_init
It will create ``database/cet_exam.db`` and pre-load 1-2 real-style samples
per (level, section) pair so the app boots with content immediately.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "database" / "cet_exam.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS vocabulary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level TEXT NOT NULL,
    word TEXT NOT NULL,
    phonetic TEXT,
    pos TEXT,
    translation TEXT,
    frequency INTEGER DEFAULT 1,
    star_rating INTEGER DEFAULT 1,
    example_sentence TEXT,
    example_translation TEXT,
    tags TEXT,
    -- Memory system fields (added in v1.6 for the quiz / wrong-book
    -- feature set). Default 0 keeps the old rows compatible.
    mastered INTEGER DEFAULT 0,
    wrong_count INTEGER DEFAULT 0,
    consec_correct INTEGER DEFAULT 0,
    last_seen_at TIMESTAMP
);

-- A separate "wrong book" table is overkill — the spec only requires
-- showing words with wrong_count > 0 — so we keep it as a virtual
-- view so the UI can just query ``SELECT ... WHERE wrong_count > 0``.
-- No additional table needed.

CREATE TABLE IF NOT EXISTS writing (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level TEXT NOT NULL,
    year INTEGER NOT NULL,
    session TEXT,
    topic TEXT,
    requirements TEXT,
    sample_essay TEXT,
    key_phrases TEXT,
    category TEXT
);
-- ``exam_type`` (alias of level) and ``title`` (short subject line)
-- and ``highlights`` (JSON: list of {"text":..., "reason":...}) are
-- added by migration in init_database() so old rows keep working.

CREATE TABLE IF NOT EXISTS reading (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level TEXT NOT NULL,
    year INTEGER NOT NULL,
    session TEXT,
    passage_title TEXT,
    passage TEXT,
    questions TEXT,
    answers TEXT,
    analysis TEXT,
    topic_type TEXT
);
-- ``exam_type`` and ``options`` (JSON list of 4-option dicts) and
-- ``answer`` (single-letter "B" form) are added by migration.

CREATE TABLE IF NOT EXISTS listening (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level TEXT NOT NULL,
    year INTEGER NOT NULL,
    session TEXT,
    section TEXT,
    audio_script TEXT,
    audio_file TEXT,           -- path to the synced .mp3, set by crawler.generate_listening_audio
    questions TEXT,
    answers TEXT,
    analysis TEXT,
    topic_type TEXT
);

CREATE TABLE IF NOT EXISTS translation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level TEXT NOT NULL,
    year INTEGER NOT NULL,
    session TEXT,
    chinese_text TEXT,
    english_reference TEXT,
    key_points TEXT,
    analysis TEXT,
    topic_type TEXT
);
-- ``exam_type`` (alias of level) and ``english_translation`` (alias
-- of english_reference) and ``key_terms`` (alias of key_points) are
-- added by migration.

CREATE TABLE IF NOT EXISTS writing_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level TEXT NOT NULL,
    predicted_topic TEXT,
    predicted_year INTEGER,
    reference_essay TEXT,
    reasoning TEXT,
    confidence INTEGER
);

CREATE TABLE IF NOT EXISTS generated_practice (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id INTEGER,
    section TEXT NOT NULL,
    level TEXT NOT NULL,
    title TEXT,
    content TEXT,
    answers TEXT,
    analysis TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Per-question answer history. Populated by the web/desktop practice
-- flows whenever the user submits an answer; used for the score banner
-- ("累计 N 题 · 正确率 X%") and any future learning-curve chart.
CREATE TABLE IF NOT EXISTS practice_attempts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    item_type      TEXT NOT NULL,         -- 'reading' | 'listening'
    item_id        INTEGER NOT NULL,      -- FK to reading.id / listening.id
    level          TEXT NOT NULL,         -- 'CET4' | 'CET6'
    q_index        INTEGER NOT NULL,      -- 0-based question index within item
    user_answer    TEXT,                  -- 'A'..'D' or NULL if skipped
    correct_answer TEXT,                  -- 'A'..'D'
    is_correct     INTEGER NOT NULL,      -- 0 / 1
    source         TEXT DEFAULT 'web',    -- 'web' | 'desktop' | 'mobile'
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_attempts_item       ON practice_attempts(item_type, item_id);
CREATE INDEX IF NOT EXISTS idx_attempts_level_time ON practice_attempts(level, created_at DESC);
"""

VOCAB_SEED = [
    # CET-4 高频核心词 (近10年真题)
    ("CET4", "contribute", "/kənˈtrɪbjuːt/", "v.", "贡献;捐献;促成", 142, 5,
     "Everyone is encouraged to contribute ideas to the project.",
     "鼓励每个人都为这个项目贡献想法。", "高频,动词"),
    ("CET4", "opportunity", "/ˌɒpəˈtjuːnəti/", "n.", "机会;时机", 138, 5,
     "Education provides equal opportunity for everyone.",
     "教育为每个人提供平等的机会。", "高频,名词"),
    ("CET4", "environment", "/ɪnˈvaɪrənmənt/", "n.", "环境;周围状况", 125, 5,
     "We must protect the environment for future generations.",
     "我们必须为子孙后代保护环境。", "高频,名词"),
    ("CET4", "technology", "/tekˈnɒlədʒi/", "n.", "技术;科技", 118, 5,
     "Modern technology has changed the way we communicate.",
     "现代科技改变了我们的交流方式。", "高频,名词"),
    ("CET4", "communicate", "/kəˈmjuːnɪkeɪt/", "v.", "交流;沟通", 96, 4,
     "It's important to communicate clearly with your team.",
     "与团队清晰沟通非常重要。", "高频,动词"),
    ("CET4", "efficient", "/ɪˈfɪʃnt/", "adj.", "高效的;效率高的", 78, 4,
     "This new method is more efficient than the old one.",
     "这个新方法比旧的更高效。", "高频,形容词"),
    ("CET4", "available", "/əˈveɪləbl/", "adj.", "可获得的;有空的", 88, 4,
     "Tickets are still available for tonight's show.",
     "今晚演出的票还有。", "高频,形容词"),
    ("CET4", "economic", "/ˌiːkəˈnɒmɪk/", "adj.", "经济的;经济学的", 65, 3,
     "The country is facing serious economic challenges.",
     "该国正面临严重的经济挑战。", "中等,形容词"),
    ("CET4", "behavior", "/bɪˈheɪvjər/", "n.", "行为;表现", 54, 3,
     "His behavior at the meeting was unprofessional.",
     "他在会议上的行为不专业。", "中等,名词"),
    ("CET4", "appreciate", "/əˈpriːʃieɪt/", "v.", "欣赏;感激", 72, 4,
     "I really appreciate your help on this project.",
     "我非常感谢你在这个项目上的帮助。", "高频,动词"),
    ("CET4", "familiar", "/fəˈmɪliə(r)/", "adj.", "熟悉的;通晓的", 45, 3,
     "Her face looks familiar, but I can't remember her name.",
     "她的脸看起来很熟悉,但我想不起她的名字。", "中等,形容词"),
    ("CET4", "achieve", "/əˈtʃiːv/", "v.", "达到;实现", 82, 4,
     "She worked hard to achieve her dream.",
     "她努力工作以实现自己的梦想。", "高频,动词"),
    ("CET4", "balance", "/ˈbæləns/", "n./v.", "平衡;权衡", 58, 3,
     "It's important to balance work and life.",
     "平衡工作与生活很重要。", "中等"),
    ("CET4", "eliminate", "/ɪˈlɪmɪneɪt/", "v.", "消除;消灭", 35, 2,
     "We need to eliminate all possible errors.",
     "我们需要消除所有可能的错误。", "低频,动词"),
    ("CET4", "fundamental", "/ˌfʌndəˈmentl/", "adj.", "基本的;根本的", 28, 2,
     "Honesty is a fundamental principle in our company.",
     "诚实是我们公司的基本原则。", "低频,形容词"),

    # CET-6 高频核心词
    ("CET6", "comprehensive", "/ˌkɒmprɪˈhensɪv/", "adj.", "综合的;全面的;理解的", 110, 5,
     "The book provides a comprehensive overview of modern history.",
     "这本书对现代史进行了全面的概述。", "高频,形容词"),
    ("CET6", "substantial", "/səbˈstænʃl/", "adj.", "大量的;实质的;坚固的", 88, 5,
     "She received a substantial inheritance from her aunt.",
     "她从姑母那里继承了一笔可观的遗产。", "高频,形容词"),
    ("CET6", "controversial", "/ˌkɒntrəˈvɜːʃl/", "adj.", "有争议的;引起争论的", 75, 4,
     "The new law has been highly controversial.",
     "这项新法律一直备受争议。", "高频,形容词"),
    ("CET6", "inevitable", "/ɪnˈevɪtəbl/", "adj.", "不可避免的;必然的", 65, 4,
     "Some changes are inevitable as you grow older.",
     "随着年龄的增长,一些变化是不可避免的。", "高频,形容词"),
    ("CET6", "subsequent", "/ˈsʌbsɪkwənt/", "adj.", "随后的;后来的", 52, 4,
     "The subsequent events proved him right.",
     "随后发生的事件证明他是正确的。", "高频,形容词"),
    ("CET6", "implement", "/ˈɪmplɪment/", "v.", "实施;执行;使生效", 95, 5,
     "The government plans to implement the new policy next month.",
     "政府计划下个月实施这项新政策。", "高频,动词"),
    ("CET6", "manipulate", "/məˈnɪpjuleɪt/", "v.", "操纵;操作;篡改", 48, 3,
     "He tried to manipulate the data to support his theory.",
     "他试图篡改数据来支持他的理论。", "中等,动词"),
    ("CET6", "advocate", "/ˈædvəkeɪt/", "v./n.", "提倡;拥护;倡导者", 58, 4,
     "She advocates for equal rights for all.",
     "她倡导人人享有平等权利。", "高频"),
    ("CET6", "compromise", "/ˈkɒmprəmaɪz/", "n./v.", "妥协;折中;损害", 62, 4,
     "Both sides reached a compromise after long negotiations.",
     "经过长时间谈判,双方达成了妥协。", "高频"),
    ("CET6", "phenomenon", "/fəˈnɒmɪnən/", "n.", "现象;奇迹", 55, 3,
     "This is a common phenomenon in big cities.",
     "这是大城市中的普遍现象。", "中等,名词"),
    ("CET6", "distinguish", "/dɪˈstɪŋɡwɪʃ/", "v.", "区分;辨别;使杰出", 68, 4,
     "It's hard to distinguish the two paintings apart.",
     "很难把这两幅画区分开来。", "高频,动词"),
    ("CET6", "articulate", "/ɑːˈtɪkjəleɪt/", "v./adj.", "清晰地表达;发音清晰的", 35, 2,
     "She is an articulate speaker who expresses her ideas clearly.",
     "她是一个口齿伶俐、表达清晰的演讲者。", "低频"),
    ("CET6", "ambiguous", "/æmˈbɪɡjuəs/", "adj.", "模糊的;含混的", 42, 3,
     "The contract terms are deliberately ambiguous.",
     "合同条款故意含糊不清。", "中等,形容词"),
    ("CET6", "notwithstanding", "/ˌnɒtwɪθˈstændɪŋ/", "prep./adv.", "尽管;然而", 38, 3,
     "Notwithstanding the difficulties, they completed the project on time.",
     "尽管困难重重,他们按时完成了项目。", "中等"),
    ("CET6", "underestimate", "/ˌʌndərˈestɪmeɪt/", "v.", "低估;看轻", 56, 4,
     "Don't underestimate the importance of good sleep.",
     "不要低估良好睡眠的重要性。", "高频,动词"),
]

WRITING_SEED = [
    # CET-4 真题范文
    ("CET4", 2024, "6月", "校园生活/活动",
     "假设你是李华,你的英国朋友 Peter 即将参加一个国际青年文化节,他写信向你咨询应该准备什么。请给他回一封邮件,内容包括:1) 表示欢迎; 2) 推荐一到两项必带物品; 3) 介绍一个相关的中国传统文化活动。",
     "Dear Peter,\n\nI'm thrilled to hear that you've been invited to the International Youth Cultural Festival. What an exciting opportunity to experience cultural exchange!\n\nTo make the most of the festival, I'd suggest you bring two essentials. First, pack a lightweight notebook to record your impressions and reflections. Second, prepare a small gift from your hometown — it will be a wonderful ice-breaker when meeting new friends.\n\nYou might also enjoy watching a traditional Chinese tea ceremony, which beautifully demonstrates harmony and respect. It's a perfect window into Chinese culture.\n\nLooking forward to hearing about your adventure!\n\nYours,\nLi Hua",
     "thrilled, ice-breaker, harmony, reflection, adventure",
     "校园生活"),
    ("CET4", 2023, "12月", "科技/学习",
     "假设你是李华,你的美国朋友 Jack 对中国的移动支付很感兴趣,来信询问相关情况。请写一封回信,介绍移动支付在中国普及的情况、便利之处以及你的看法。",
     "Dear Jack,\n\nIt's great to receive your letter. I'm happy to share something about mobile payment in China.\n\nMobile payment, especially through apps like Alipay and WeChat Pay, has become extremely popular. Whether buying breakfast from a street vendor or paying utility bills, almost everything can be done with a single tap on the phone. It saves time, reduces the need to carry cash, and even helps people manage their spending through transaction records.\n\nFrom my perspective, mobile payment reflects how technology can transform daily life. However, we should also be cautious about data security and protect seniors who may struggle with digital tools.\n\nHope this gives you a useful picture!\n\nYours,\nLi Hua",
     "extremely, transaction, transform, cautious, data security",
     "科技"),
    # CET-6 真题范文
    ("CET6", 2024, "6月", "职场/职业发展",
     "Write an essay based on the chart below. In 2023, the proportion of college graduates choosing to start their own business was 5.2%, while 35.8% chose to pursue further studies and the rest chose to work. You should: 1) describe the chart briefly; 2) analyze the reasons; 3) give your suggestions.",
     "The bar chart presents a revealing snapshot of Chinese college graduates' choices in 2023. A modest 5.2% chose entrepreneurship, while 35.8% opted for further studies, and the remainder entered the job market directly.\n\nSeveral factors explain this distribution. First, the competitive job market has driven many graduates to pursue postgraduate degrees, hoping to gain a competitive edge. Second, the high cost and risk of starting a business, combined with limited access to capital, deter would-be entrepreneurs. Third, traditional career paths in established companies still offer stability that appeals to many.\n\nPersonally, I believe there is no single right path. Graduates should weigh their strengths, interests, and the economic reality. Universities, meanwhile, can play a larger role by offering entrepreneurship courses and mentorship programs to help young people pursue their ambitions with confidence.",
     "snapshot, opt for, competitive edge, deter, established, weigh",
     "职场"),
    ("CET6", 2023, "12月", "社会/文化",
     "Suppose you have two options upon graduation: 1) taking a well-paid job in a big city; 2) returning to your hometown to work as a village teacher. Write an essay to state your choice and explain your reasons.",
     "When facing the choice between a lucrative city job and teaching in a rural village, I would choose the latter without hesitation.\n\nThe decision rests on three considerations. To begin with, education is the cornerstone of social progress, and rural areas still suffer from a severe shortage of qualified teachers. By joining them, I can contribute directly to bridging the educational gap. Moreover, working in a village offers a unique opportunity to broaden my understanding of China beyond the urban bubble, which I believe will make me a more grounded and compassionate person. Finally, the sense of purpose that comes from watching my students grow is, in my view, far more rewarding than a comfortable salary.\n\nOf course, this path is not easy, and I respect those who choose otherwise. But for me, meaning matters more than money.",
     "lucrative, cornerstone, broaden, grounded, compassionate, rewarding",
     "社会"),
]

READING_SEED = [
    ("CET4", 2024, "6月", "Passage 1 — A New Way to Learn",
     "In the past decade, online learning has gone from a niche option to a mainstream choice for millions of students worldwide. Platforms such as Coursera, edX, and Khan Academy offer courses from top universities, often for free or at a fraction of the on-campus cost.\n\nProponents argue that online education democratizes knowledge, allowing anyone with an internet connection to study subjects once reserved for the privileged few. A working mother in a rural town, for example, can now take a computer science class from a leading tech university without leaving her job.\n\nCritics, however, point out that online learning is not without drawbacks. Many students struggle with motivation when studying alone, and the absence of in-person interaction can leave gaps in understanding. Hands-on subjects, such as laboratory sciences, remain difficult to teach purely online.\n\nMost educators now believe the future lies in a blended approach — combining online flexibility with occasional in-person workshops. This hybrid model aims to preserve the best of both worlds.",
     '[{"q":"What is the main idea of the passage?","options":["A. Online learning is replacing traditional schools.","B. Online learning has both advantages and limitations.","C. Traditional schools are still better than online platforms.","D. Online platforms are too expensive for most students."]},{"q":"According to the passage, who benefits most from online learning?","options":["A. University professors","B. People in remote or underserved areas","C. High school teachers","D. Software developers"]},{"q":"What is the author’s attitude toward the blended model?","options":["A. Doubtful","B. Supportive","C. Indifferent","D. Skeptical"]}]',
     "1. B  2. B  3. B",
     "本文讨论了在线学习的兴起、优势与不足。文章结构:第一段引出话题,第二段论述优势(民主化知识),第三段指出不足(动力、人际互动),第四段提出混合模式作为未来方向。第1题是主旨题,需概括全文;第2题定位第二段'anyone with an internet connection';第3题是态度题,'the future lies in'体现作者对混合模式的支持。",
     "教育/科技"),
    ("CET4", 2023, "12月", "Passage 2 — The Power of Habit",
     "Habits shape our daily lives more than we realize. Researchers estimate that roughly 40% of our actions each day are not conscious decisions but routine responses triggered by context — a process known as 'context-dependent repetition.'\n\nUnderstanding this can be transformative. If you want to read more, place a book on your pillow; if you want to eat healthier, keep fruit visible on the kitchen counter. The environment, not willpower, drives most behavior change.\n\nThis insight has inspired a growing industry of habit-tracking apps and books. Yet experts caution that lasting change requires more than technology. It also demands patience and self-compassion: missing a day does not erase progress, and perfectionism often backfires.",
     '[{"q":"What percentage of daily actions are habits according to the passage?","options":["A. About 20%","B. About 40%","C. About 60%","D. About 80%"]},{"q":"The author suggests that changing habits depends mainly on _____.","options":["A. Strong willpower","B. Changing the environment","C. Reading books","D. Using apps"}]',
     "1. B  2. B",
     "短文围绕习惯的力量展开。第1题为细节题,定位首段 'roughly 40%';第2题为推断题,作者在第二段强调环境对行为的塑造作用。",
     "心理/生活"),
    # CET-6 真题样例
    ("CET6", 2024, "6月", "The Future of Remote Work",
     "When the pandemic forced offices to close in 2020, few predicted that remote work would persist long after the initial shock. Yet five years on, hybrid arrangements have become a permanent fixture in many industries, with employees splitting their week between home and the office.\n\nCompanies that once feared lost productivity have largely adjusted. Studies suggest that for knowledge-based roles, output is comparable to — and sometimes exceeds — in-office levels. Workers, in turn, value the flexibility: the daily commute is replaced by family breakfasts, and geographic constraints no longer dictate career options.\n\nStill, the model has its critics. Younger employees often report feeling disconnected from mentors, and spontaneous hallway conversations — long credited as a source of innovation — are missed. Some firms are now experimenting with 'anchor days,' requiring teams to gather on specific weekdays to maintain cohesion.\n\nWhether remote work endures in its current form remains uncertain. What is clear is that the relationship between employer, employee, and workplace has been permanently redefined.",
     """[{"q":"What does the author mean by 'a permanent fixture'?","options":["A. A temporary arrangement","B. A lasting feature","C. A legal requirement","D. A casual practice"]},{"q":"Why are some companies introducing anchor days?","options":["A. To reduce office costs","B. To monitor employee attendance","C. To strengthen team cohesion","D. To comply with new laws"]},{"q":"What is the author’s overall tone?","options":["A. Critical","B. Analytical","C. Sarcastic","D. Pessimistic"]}]""",
     "1. B  2. C  3. B",
     "本文探讨远程/混合办公的长期影响。第1题是词义猜测,'permanent fixture' 意为'长期存在的特征';第2题定位第三段,anchor days 旨在维护团队凝聚力;第3题是态度题,作者以事实和数据分析利弊,基调为 'analytical'(分析型)。",
     "职场"),
]

LISTENING_SEED = [
    ("CET4", 2024, "6月", "短对话 (Short Conversation)",
     "W: Have you finished reading the book I lent you last week?\nM: Yes, I finished it last night. It was really eye-opening.\nW: I told you you'd love it. So, what did you think of the ending?\nM: I was surprised at first, but it made sense after I thought about it.\nW: That's exactly how I felt. Would you recommend it to others?\nM: Absolutely. I'm planning to give my copy to my sister.",
     '[{"q":"What is the conversation mainly about?","options":["A. A book the woman lent the man","B. A movie the man watched","C. A class the woman is taking","D. A gift the man received"]},{"q":"How did the man feel about the book?","options":["A. Disappointed","B. Surprised but positive","C. Indifferent","D. Confused"]}]',
     "1. A  2. B",
     "短对话围绕女士借给男士的书展开。男士在最后表示非常推荐。",
     "校园/生活"),
    ("CET4", 2023, "12月", "长对话 (Long Conversation)",
     "W: Good morning, Sir. May I see your ticket and passport, please?\nM: Sure, here you are.\nW: Thank you. You're in seat 23A, by the window. Would you like a window seat or aisle?\nM: Window is fine. How long is the flight?\nW: About two hours and twenty minutes. We'll be serving a meal shortly after takeoff.\nM: Great. Is there Wi-Fi on board?\nW: Yes, but it's a paid service. You can purchase a one-hour pass for $5 or full flight for $12.\nM: I'll take the full flight, thanks.\nW: Very good. Here is your boarding pass. Please be at the gate no later than 30 minutes before departure.\nM: Thank you very much.",
     '[{"q":"What is the man’s seat number?","options":["A. 22A","B. 23A","C. 32A","D. 12A"]},{"q":"How much does the full-flight Wi-Fi cost?","options":["A. $5","B. $7","C. $10","D. $12"]}]',
     "1. B  2. D",
     "长对话发生在机场柜台,男士办理登机手续。",
     "出行"),
    ("CET6", 2024, "6月", "短文 (Passage)",
     "The concept of a 'four-day work week' is no longer a fantasy. In recent years, companies in Iceland, the United Kingdom, and New Zealand have piloted the model with remarkable results: productivity remained stable or even rose, while employee stress and burnout dropped sharply.\n\nProponents argue that compressed schedules force teams to eliminate unnecessary meetings and focus on outcomes. Critics, however, warn that some industries — particularly customer service and healthcare — cannot easily adopt the model without compromising service quality.\n\nResearchers now suggest that the success of the four-day week depends less on the calendar and more on management culture. Companies that prioritize trust, clear goals, and asynchronous communication tend to thrive, while those that simply cut hours without restructuring work often see diminishing returns.\n\nThe lesson is clear: a shorter week is a destination, not a starting point.",
     '[{"q":"What is the passage mainly about?","options":["A. The history of the five-day work week","B. The results of four-day work week trials","C. How to cut meetings","D. Why Iceland works less"]},{"q":"According to the passage, what is the key to a successful four-day week?","options":["A. Higher salaries","B. Better technology","C. Management culture and trust","D. More customers"]},{"q":"What does the author mean by the last sentence?","options":["A. Companies should start with a shorter week immediately.","B. Reducing hours alone won’t work without deeper changes.","C. Workers should aim for the weekend.","D. Four-day weeks are unrealistic."]}]',
     "1. B  2. C  3. B",
     "短文围绕四天工作制展开,重点是其试验结果与成功条件。最后一句的隐含意思是'减少工时只是结果,而不是起点',即仅减少工时是不够的,需要更深层次的改革。",
     "职场"),
]

TRANSLATION_SEED = [
    ("CET4", 2024, "6月", "中国的移动支付在过去十年中发展迅速。如今,无论是在大型商场还是街边小店,人们都可以通过手机完成付款。这不仅方便了日常生活,也推动了无现金社会的发展。",
     "China's mobile payment has developed rapidly over the past decade. Nowadays, people can complete transactions by mobile phone in both large shopping malls and small street shops. This has not only facilitated daily life but also promoted the development of a cashless society.",
     "在过去十年中: over the past decade; 推动: promote; 无现金社会: cashless society; 不仅...也...: not only... but also...",
     "重点词汇:mobile payment, transaction, cashless society。常用句型:'在过去十年中' 'It is + adj + to do'。",
     "科技"),
    ("CET4", 2023, "12月", "端午节是中国最古老的传统节日之一,至今已有 2000 多年的历史。人们在节日期间会赛龙舟、吃粽子,以纪念古代诗人屈原。这个节日也体现了中国人民对家庭和自然的尊重。",
     "The Dragon Boat Festival is one of the oldest traditional festivals in China, with a history of more than 2,000 years. During the festival, people hold dragon boat races and eat zongzi to commemorate the ancient poet Qu Yuan. The festival also reflects the Chinese people's respect for family and nature.",
     "端午节: the Dragon Boat Festival; 赛龙舟: hold dragon boat races; 纪念: commemorate; 体现: reflect; 尊重: respect",
     "文化类翻译常考。重点词组:dragon boat races, commemorate, with a history of more than 2,000 years。",
     "文化"),
    ("CET6", 2024, "6月", "随着经济的快速发展,越来越多的城市面临着交通拥堵问题。政府部门正在采取多种措施来缓解这一状况,包括完善公共交通系统、推广共享出行,以及实施智能化交通管理。",
     "With rapid economic development, an increasing number of cities are facing the problem of traffic congestion. Government departments are adopting various measures to alleviate the situation, including improving public transportation systems, promoting shared mobility, and implementing intelligent traffic management.",
     "随着: with; 交通拥堵: traffic congestion; 缓解: alleviate; 完善: improve; 共享出行: shared mobility; 智能化交通管理: intelligent traffic management",
     "社会热点类翻译。注意 with 引导的伴随状语; '多种措施' 翻译为 various measures; '推广' 用 promote。",
     "社会"),
    ("CET6", 2023, "12月", "中国的高铁建设取得了举世瞩目的成就。截至 2022 年底,中国高铁运营里程已超过 4 万公里,居世界首位。高铁不仅缩短了城市之间的距离,也带动了沿线地区的经济发展。",
     "China's high-speed rail construction has achieved remarkable accomplishments that have attracted worldwide attention. By the end of 2022, the operating mileage of China's high-speed rail had exceeded 40,000 kilometers, ranking first in the world. High-speed rail has not only shortened the distance between cities but also driven the economic development of regions along the lines.",
     "举世瞩目的: attracting worldwide attention; 运营里程: operating mileage; 居世界首位: rank first in the world; 缩短: shorten; 带动: drive",
     "数字翻译要点:By the end of + 时间; 居首位翻译为 rank first。注意时态:过去完成时 had exceeded。",
     "科技/经济"),
]

PREDICTION_SEED = [
    ("CET4", "人工智能与教育", 2026,
     "The rapid rise of artificial intelligence is reshaping the way we learn. From personalized tutoring apps to AI assistants that answer questions 24/7, technology is no longer a supplement to education — it is becoming its backbone.\n\nHowever, the human element remains irreplaceable. AI can deliver content, but it cannot inspire curiosity the way a passionate teacher can. It can correct grammar, but it cannot teach students to think critically about the world.\n\nThe future of education, I believe, lies in collaboration: AI handles routine tasks, while teachers focus on mentorship, creativity, and emotional guidance. The students who thrive will be those who learn to work with intelligent machines, not against them.",
     "命题依据:(1) 2018-2024 四级写作真题中,科技类话题占比超过 35%; (2) ChatGPT、DeepSeek 在 2023-2025 引发全球讨论,成为社会焦点; (3) 中国教育部 2025 年发布《AI+教育行动计划》。",
     78),
    ("CET4", "中国传统文化走向世界", 2026,
     "In recent years, traditional Chinese culture has taken the world stage by storm. From Hanfu fashion shows in Paris to kungfu performances on global streaming platforms, China's cultural soft power is reaching new audiences.\n\nThis trend is no accident. Young Chinese, proud of their heritage, are reinventing tradition through TikTok videos, animated films, and creative merchandise. Such grassroots efforts have done more for cultural exchange than official programs alone.\n\nTo keep this momentum, we should support creators, protect intangible heritage, and invite the world to experience China's past and present. Culture, after all, is a bridge — and every story shared is a step closer between peoples.",
     "命题依据:2022 北京冬奥、2023 杭州亚运、2024 巴黎奥运中国代表团文化展示,以及 2025 年春节申遗成功,均为可考热点。",
     72),
    ("CET6", "数字经济与就业转型", 2026,
     "The digital economy now accounts for more than 40% of China's GDP, and its rise is fundamentally reshaping the labor market. Routine clerical and manufacturing jobs are giving way to roles in data analysis, platform operations, and AI oversight.\n\nThis shift brings both opportunity and anxiety. On the one hand, new professions command higher salaries and offer greater flexibility. On the other, millions of mid-career workers risk being left behind, lacking the digital fluency that younger entrants take for granted.\n\nPolicymakers and businesses must therefore act on two fronts: invest in reskilling programs, and design social safety nets for those whose jobs disappear. Lifelong learning, in this new era, is not a luxury but a necessity.",
     "命题依据:(1) 2023-2025 年官方数据反复提及'数字经济'; (2) 六级写作偏好分析图表 + 论述结构; (3) 就业焦虑为青年普遍议题。",
     80),
    ("CET6", "心理健康:被忽视的公共议题", 2026,
     "Mental health has long been treated as a private matter, something to be discussed behind closed doors. But mounting research suggests it is, in fact, a public issue with sweeping social and economic consequences.\n\nIn schools, anxiety and depression are rising sharply among adolescents. In workplaces, burnout costs the global economy an estimated one trillion dollars each year. The cost of silence, in short, is enormous.\n\nReal change requires collective action. Governments should fund accessible counseling; employers should normalize mental-health days; families should listen without judgment. A society that takes care of its people's minds is, in the end, a society that takes care of its future.",
     "命题依据:(1) WHO 2024 年报告将心理健康列为全球公共卫生优先事项; (2) 中国 2024 年《青少年心理健康蓝皮书》引发关注; (3) 六级写作近年倾向抽象议题。",
     75),
]


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_database(force: bool = False) -> None:
    """Create tables and load seed data."""
    if force and DB_PATH.exists():
        os.remove(DB_PATH)
    conn = _connect()
    try:
        conn.executescript(SCHEMA_SQL)
        # Migrations for tables that already exist from an older version
        # of the project. Safe to run multiple times (SQLite ignores
        # duplicate column errors only when guarded; we use a check
        # via PRAGMA table_info).
        # ---------- vocabulary ----------
        existing_cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(vocabulary)").fetchall()
        }
        migrations = [
            ("mastered",         "INTEGER DEFAULT 0"),
            ("wrong_count",      "INTEGER DEFAULT 0"),
            ("consec_correct",   "INTEGER DEFAULT 0"),
            ("last_seen_at",     "TIMESTAMP"),
            # SM-2 spaced repetition (added in v1.7). ``easiness`` and
            # ``interval`` are the two working variables; ``due_date`` is
            # ``last_seen_at + interval`` computed at review time. NULL
            # means "never reviewed" — those rows are treated as "due now"
            # by the SM-2 selector.
            ("easiness",         "REAL DEFAULT 2.5"),
            ("interval_days",    "INTEGER DEFAULT 0"),
            ("due_date",         "TIMESTAMP"),
        ]
        for col, decl in migrations:
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE vocabulary ADD COLUMN {col} {decl}")
        # ---------- writing ----------
        existing_cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(writing)").fetchall()
        }
        for col, decl in [
            ("exam_type", "TEXT"),
            ("title",     "TEXT"),
            ("highlights", "TEXT"),  # JSON list
        ]:
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE writing ADD COLUMN {col} {decl}")
        # ---------- reading ----------
        existing_cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(reading)").fetchall()
        }
        for col, decl in [
            ("exam_type", "TEXT"),
            ("options",   "TEXT"),
            ("answer",    "TEXT"),
        ]:
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE reading ADD COLUMN {col} {decl}")
        # ---------- translation ----------
        existing_cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(translation)").fetchall()
        }
        for col, decl in [
            ("exam_type",          "TEXT"),
            ("english_translation", "TEXT"),
            ("key_terms",          "TEXT"),
        ]:
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE translation ADD COLUMN {col} {decl}")
        # ---------- listening ----------
        existing_cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(listening)").fetchall()
        }
        if "audio_file" not in existing_cols:
            conn.execute(
                "ALTER TABLE listening ADD COLUMN audio_file TEXT"
            )
        conn.commit()
        # Seed only if tables are empty
        for sql, rows in [
            ("SELECT COUNT(*) FROM vocabulary", VOCAB_SEED),
            ("SELECT COUNT(*) FROM writing", WRITING_SEED),
            ("SELECT COUNT(*) FROM reading", READING_SEED),
            ("SELECT COUNT(*) FROM listening", LISTENING_SEED),
            ("SELECT COUNT(*) FROM translation", TRANSLATION_SEED),
            ("SELECT COUNT(*) FROM writing_predictions", PREDICTION_SEED),
        ]:
            cur = conn.execute(sql)
            (count,) = cur.fetchone()
            if count == 0 and rows:
                # pick the right table name from the SQL
                table = sql.split("FROM")[1].strip()
                cols = {
                    "vocabulary": "(level,word,phonetic,pos,translation,frequency,star_rating,example_sentence,example_translation,tags)",
                    "writing": "(level,year,session,topic,requirements,sample_essay,key_phrases,category)",
                    "reading": "(level,year,session,passage_title,passage,questions,answers,analysis,topic_type)",
                    "listening": "(level,year,session,section,audio_script,questions,answers,analysis,topic_type)",
                    "translation": "(level,year,session,chinese_text,english_reference,key_points,analysis,topic_type)",
                    "writing_predictions": "(level,predicted_topic,predicted_year,reference_essay,reasoning,confidence)",
                }[table]
                conn.executemany(
                    f"INSERT INTO {table} {cols} VALUES ({','.join(['?']*len(rows[0]))})",
                    rows,
                )
        conn.commit()
    finally:
        conn.close()
    print(f"[db_init] Database ready at {DB_PATH}")


if __name__ == "__main__":
    init_database(force=True)
