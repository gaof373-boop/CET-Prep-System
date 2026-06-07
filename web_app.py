"""📱 CET 智胜 · 网页版 (Streamlit) 移动端入口

【架构原则】
    1. 绝对隔离: 不 import ui.views 或 tkinter 任何东西
    2. 业务复用: 直接 import core.data_manager / core.ai_service
       → 桌面版的所有 SQLite 查询、AI 调用、生词捕捉逻辑
         100% 复用,网页版只负责"换皮"
    3. 移动优先:  所有页面按手机宽度(< 768px)优先排版

【启动方式】
    cd D:\\CET-Prep-System
    streamlit run web_app.py
    # 浏览器自动打开 http://localhost:8501
    # 手机访问: 同一局域网下, 把 8501 端口映射出去即可
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

# Ensure project root is on sys.path so `core.*` resolves
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# CRITICAL: chdir into the project root BEFORE importing core.*,
# so the main DB at <root>/database/cet_exam.db is always found,
# even if the user starts streamlit from another directory.
import os  # noqa: E402
os.chdir(PROJECT_ROOT)

import streamlit as st  # noqa: E402

from core.data_manager import DataManager, parse_answer_letters  # noqa: E402
from core.ai_service import AIService  # noqa: E402
from core.db_init import DB_PATH, init_database  # noqa: E402

# Force the DB to exist (no-op if it already does). This means
# launching `streamlit run web_app.py` from a clean checkout
# still ends up with a usable schema.
init_database()

# Streamlit page config MUST be the first st.* call
st.set_page_config(
    page_title="CET 智胜 · 移动备考",
    page_icon="📱",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": "CET 智胜 V2.1 · 网页版 · 基于 Streamlit + 桌面版数据/AI 复用",
    },
)


# ===========================================================================
# Session bootstrap (run once per browser session)
# ===========================================================================
@st.cache_resource
def get_data_manager() -> DataManager:
    """Cache the DataManager — it owns a long-lived SQLite connection.

    Always bind to the MAIN database (``<PROJECT_ROOT>/database/cet_exam.db``)
    so the desktop client and the web client see EXACTLY the same data:
    mastered words, wrong-counts, AI grades, etc.
    """
    dm = DataManager(db_path=DB_PATH)
    # Sanity log so the operator can see which DB is live
    print(f"[web_app] DataManager bound to {dm.db_path}")
    return dm


@st.cache_resource
def get_ai_service() -> AIService:
    return AIService()


dm: DataManager = get_data_manager()
ai: AIService = get_ai_service()

# Level state — default CET-4
if "level" not in st.session_state:
    st.session_state.level = "CET-4"
if "quiz_state" not in st.session_state:
    st.session_state.quiz_state = None  # dict or None
if "practice_state" not in st.session_state:
    # One sub-dict per practice item, keyed f"{kind}:{item_id}".
    # Shape: {"answers": {q_index: option_text}, "submitted": bool,
    #         "ai_reports": {q_index: dict}}
    st.session_state.practice_state = {}


# ===========================================================================
# UI helpers
# ===========================================================================
def _mobile_metric_card(label: str, value: int, accent: str, hint: str = "") -> None:
    """Streamlit-native metric card with custom CSS accent color."""
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, {accent}22 0%, {accent}05 100%);
            border-left: 4px solid {accent};
            border-radius: 10px;
            padding: 18px 20px;
            margin-bottom: 8px;
        ">
            <div style="font-size:14px; color:#6B7280; margin-bottom:4px;">{label}</div>
            <div style="font-size:36px; font-weight:700; color:{accent};">{value:,}</div>
            <div style="font-size:11px; color:#9CA3AF; margin-top:4px;">{hint}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


QUOTES = [
    "今天也是充满斗志的一天!你已累计在系统内斩落 {n} 个核心考点。",
    "水滴石穿,绳锯木断。再小的进步,都是通往 600+ 路上的真金白银。",
    "英语学习没有速成,只有每天 30 分钟的坚持。",
    "不怕慢,只怕站。今天你比昨天多记 5 个词,12 月考场你就会多 5 分底气。",
    "CET 不是天赋的较量,是习惯的较量 — 系统陪你把习惯刻进日历。",
    "你不需要完美,你只需要今天比昨天多坚持 10 分钟。",
    "错题本不是伤疤,是勋章 — 每一道你不再错的题,都是勋章上的一颗星。",
]


def _render_dashboard() -> None:
    """V2.2 学霸看板 — native st.metric × 4 columns + delta indicators.

    Uses Streamlit's built-in ``st.metric`` so the cards are perfectly
    responsive on mobile and look like the official Streamlit dashboard.
    """
    level = st.session_state.level.replace("-", "")
    stats = dm.dashboard_stats(level=level)

    # ----- Hero header -----
    st.markdown("## 📊 学霸备考数据看板")
    st.caption(f"当前级别: **{st.session_state.level}** · 你的今日战况")

    # ----- 4 native metric cards (Streamlit handles mobile reflow) -----
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(
            label="🎯 已掌握词汇",
            value=f"{stats['mastered']:,}",
            delta=f"{(stats['mastered'] / max(1, stats['total_words']) * 100):.1f}%",
            delta_color="normal",
            help="点击「📝 词汇板块」标记 ✓ 已掌握",
        )
    with c2:
        st.metric(
            label="🟥 错题攻坚",
            value=f"{stats['wrong_book']:,}",
            delta="点击巩固 →",
            delta_color="inverse",
            help="错题数越高,说明薄弱点越多,赶紧去「🟥 错题本」反复练!",
        )
    with c3:
        st.metric(
            label="📚 刷题成就",
            value=f"{stats['practice_reading'] + stats['practice_listening']:,}",
            delta=f"阅读 {stats['practice_reading']} · 听力 {stats['practice_listening']}",
            delta_color="off",
            help="阅读 + 听力总题数",
        )
    with c4:
        ai_total = stats['ai_essay_grades'] + stats['ai_trans_grades']
        st.metric(
            label="🤖 AI 助攻频次",
            value=f"{ai_total:,}",
            delta=f"写作 {stats['ai_essay_grades']} · 翻译 {stats['ai_trans_grades']}",
            delta_color="off",
            help="写作批改 + 翻译精批 累计",
        )

    # ----- DB connection banner (lets the user verify which DB is live) -----
    with st.expander("🗄️ 数据源 / Database", expanded=False):
        st.code(f"主库路径: {dm.db_path}\n词库总量: {stats['total_words']:,} 词", language="text")

    # ----- Motivational quote -----
    n_total = stats["total_words"]
    quote = random.choice(QUOTES).format(n=n_total)
    st.info(f"💪 {quote}")

    # ----- Refresh button -----
    if st.button("🔄 刷新数据", use_container_width=True):
        st.cache_resource.clear()
        st.rerun()


# ===========================================================================
# Vocabulary + Quiz
# ===========================================================================
def _pick_quiz_word(level: str) -> dict | None:
    """Pick one random word, balanced between mastered/wrong/new."""
    import random as _r
    pool = dm.list_vocabulary(level, min_star=1)
    if not pool:
        return None
    return _r.choice(pool)


def _render_vocabulary_tab() -> None:
    level = st.session_state.level.replace("-", "")
    st.markdown(f"### 📝 词汇板块 · {level}")

    # filter row
    cols = st.columns([2, 1, 1])
    search = cols[0].text_input("🔍 搜索单词 / 中文", "")
    min_star = cols[1].slider("最低星级", 1, 5, 1)
    only_wrong = cols[2].checkbox("只看错题本", False)

    # query
    try:
        words = dm.list_vocabulary(
            level, min_star=min_star,
            search=search.strip() or None,
        )
    except Exception as e:
        st.error(f"查询失败: {e}")
        return

    if only_wrong:
        wrong_words = {w["word"] for w in dm.list_wrong_book(level)}
        words = [w for w in words if w["word"] in wrong_words]

    st.caption(f"共 {len(words)} 个词")

    if not words:
        st.warning("没有匹配的单词。请调整筛选条件。")
        return

    # paginated display
    PAGE = 30
    if "vocab_page" not in st.session_state:
        st.session_state.vocab_page = 0
    max_page = max(0, (len(words) - 1) // PAGE)
    if st.session_state.vocab_page > max_page:
        st.session_state.vocab_page = 0
    page = st.session_state.vocab_page
    slice_ = words[page * PAGE: (page + 1) * PAGE]

    # build dataframe-friendly view
    import pandas as pd
    df_rows = []
    for w in slice_:
        df_rows.append({
            "⭐": w.get("star_rating", 0),
            "单词": w.get("word", ""),
            "音标": w.get("phonetic", ""),
            "中文": w.get("translation", "") or "(暂无)",
            "频率": w.get("frequency", 0),
            "已掌握": "✅" if w.get("mastered") else "❌",
            "错题": int(w.get("wrong_count", 0) or 0),
            "id": w.get("id"),
        })
    df = pd.DataFrame(df_rows)
    st.dataframe(df.drop(columns=["id"]), use_container_width=True, hide_index=True)

    # master toggle per visible page
    st.markdown("##### 标记掌握")
    pick_cols = st.columns(5)
    for i, w in enumerate(slice_[:10]):
        with pick_cols[i % 5]:
            label = f"✓ {w['word']}" if not w.get("mastered") else f"⛔ {w['word']}"
            if st.button(label, key=f"master_{w['id']}_{page}",
                         use_container_width=True):
                dm.toggle_mastered(w["id"])
                st.rerun()

    # pagination
    pcol1, pcol2, pcol3 = st.columns([1, 2, 1])
    with pcol1:
        if st.button("◀ 上一页", disabled=page == 0, use_container_width=True):
            st.session_state.vocab_page = max(0, page - 1)
            st.rerun()
    with pcol2:
        st.markdown(f"<center>第 {page + 1} / {max_page + 1} 页</center>",
                    unsafe_allow_html=True)
    with pcol3:
        if st.button("下一页 ▶", disabled=page >= max_page, use_container_width=True):
            st.session_state.vocab_page = min(max_page, page + 1)
            st.rerun()


def _render_quiz_tab() -> None:
    level = st.session_state.level.replace("-", "")
    st.markdown(f"### 🎲 背单词自测 · {level}")

    mode = st.radio("出题方向", ["英 → 中", "中 → 英"],
                    horizontal=True)

    if st.button("🎯 抽一题", type="primary", use_container_width=True):
        word = _pick_quiz_word(level)
        if not word:
            st.error("词库为空")
            return
        st.session_state.quiz_state = {
            "word": word,
            "direction": mode,
            "answer_revealed": False,
            "user_input": "",
        }

    qs = st.session_state.quiz_state
    if not qs:
        st.info("点击「🎯 抽一题」开始一次盲测。")
        return

    word = qs["word"]
    direction = qs["direction"]
    if direction == "英 → 中":
        prompt = word.get("word", "")
        answer = word.get("translation", "") or "(无中文释义)"
    else:
        prompt = word.get("translation", "") or "(无中文释义)"
        answer = word.get("word", "")

    st.markdown(f"#### 题目")
    st.markdown(
        f"<div style='font-size:28px; font-weight:700; "
        f"padding:20px; background:#F1F5F9; border-radius:10px; "
        f"text-align:center; color:#0F172A;'>{prompt}</div>",
        unsafe_allow_html=True,
    )

    user_ans = st.text_input("✍️ 你的答案", value=qs.get("user_input", ""),
                              key="quiz_input")
    qs["user_input"] = user_ans

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("✅ 我答对了", use_container_width=True):
            try:
                dm.record_correct(word["id"])
            except Exception:
                pass
            qs["answer_revealed"] = True
            st.success("✓ 记录为正确")
    with c2:
        if st.button("❌ 我答错了", use_container_width=True):
            try:
                dm.record_wrong(word["id"])
            except Exception:
                pass
            qs["answer_revealed"] = True
            st.warning("已加入错题本")
    with c3:
        if st.button("🔓 显示答案", use_container_width=True):
            qs["answer_revealed"] = True

    if qs["answer_revealed"]:
        st.markdown("##### 参考答案")
        st.markdown(
            f"<div style='font-size:20px; padding:12px; "
            f"background:#ECFDF5; border-left:4px solid #10B981; "
            f"border-radius:6px; color:#065F46;'>{answer}</div>",
            unsafe_allow_html=True,
        )
        st.caption(f"⭐ {word.get('star_rating', 0)} · "
                   f"频率 {word.get('frequency', 0)} · "
                   f"已掌握 {'✅' if word.get('mastered') else '❌'}")


# ===========================================================================
# AI Grader
# ===========================================================================
def _render_ai_grader() -> None:
    st.markdown("## 🤖 AI 写作 / 翻译批改官")
    st.caption("手机端手写录入 → 一键 AI 精批 → 红色纠错报告")

    if not ai.has_api():
        st.warning("⚠️ 未配置 API Key,将使用本地启发式评分。"
                   "点击左侧「🔑 API 配置」可填入 OpenAI 兼容接口。")

    task = st.radio("批改模式", ["✍️ 写作批改", "🗣️ 翻译精批"],
                    horizontal=True)

    if task == "✍️ 写作批改":
        _render_essay_grader()
    else:
        _render_translation_grader()


def _render_essay_grader() -> None:
    st.markdown("#### ✍️ 写作 AI 精批")
    level = st.session_state.level.replace("-", "")
    topic = st.text_input("📌 题目 (可选)", value="")
    essay = st.text_area("✍️ 你的作文 (建议 80 词以上)",
                         height=240,
                         placeholder="Paste / type your essay here ...")

    if st.button("🤖 提交 AI 批改", type="primary", use_container_width=True):
        if len(essay.strip()) < 30:
            st.error("作文太短,至少 30 字符。")
            return
        with st.spinner("AI 老师正在精批,请稍候..."):
            try:
                result = ai.grade_essay(essay, topic=topic, level=level)
            except Exception as e:
                st.error(f"AI 批改失败: {e}")
                return
        if not result:
            st.warning("AI 返回空,使用本地启发式兜底。")
            result = {"score": 0, "highlights": [], "summary": "本地兜底评分"}
        _render_essay_report(result)


def _render_essay_report(r: dict) -> None:
    """Display AI essay report in a markdown-friendly mobile layout."""
    score = r.get("score", 0)
    color = "#10B981" if score >= 12 else "#F59E0B" if score >= 8 else "#EF4444"
    st.markdown(
        f"""
        <div style="padding:20px; background:linear-gradient(135deg, {color}22, {color}05);
                    border-left:4px solid {color}; border-radius:10px; margin-bottom:12px;">
            <div style="font-size:14px; color:#6B7280;">综合评分</div>
            <div style="font-size:48px; font-weight:700; color:{color};">{score} / 15</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if r.get("summary"):
        st.markdown("##### 📝 总评")
        st.info(r["summary"])

    if r.get("highlights"):
        st.markdown("##### 🟥 逐句纠错")
        for h in r["highlights"]:
            if isinstance(h, dict):
                st.markdown(
                    f"- **原句**: {h.get('original', '')}\n"
                    f"  - ❌ {h.get('issue', '')}\n"
                    f"  - ✅ {h.get('fix', '')}"
                )
            else:
                st.markdown(f"- {h}")

    if r.get("upgrades"):
        st.markdown("##### 💎 替换建议")
        for u in r["upgrades"]:
            if isinstance(u, dict):
                st.markdown(
                    f"- `{u.get('from','')}` → **`{u.get('to','')}`**"
                    f" ({u.get('reason','')})"
                )
            else:
                st.markdown(f"- {u}")

    if r.get("polished"):
        st.markdown("##### 🌟 润色版")
        st.success(r["polished"])


def _render_translation_grader() -> None:
    st.markdown("#### 🗣️ 翻译 AI 逐句精批")
    level = st.session_state.level.replace("-", "")
    zh = st.text_area("📥 中文原文", height=100,
                       placeholder="要翻译的中文段落 ...")
    ref = st.text_area("📤 参考译文 (可选)", height=100,
                        placeholder="(留空则 AI 自动生成参考译文)")
    student = st.text_area("✍️ 你的翻译", height=160,
                            placeholder="Your English translation ...")

    if st.button("🤖 提交 AI 精批", type="primary", use_container_width=True):
        if not zh.strip() or not student.strip():
            st.error("中文原文和你的翻译都不能为空。")
            return
        with st.spinner("AI 老师正在逐句精批..."):
            try:
                result = ai.grade_translation_line_by_line(
                    zh, ref or "", student
                )
            except Exception as e:
                st.error(f"AI 批改失败: {e}")
                return
        if not result:
            st.warning("AI 返回空,使用本地启发式兜底。")
            result = {"summary": "(本地兜底)", "missing_points": [],
                       "chinglish": [], "upgrades": [], "polished": student}
        _render_translation_report(result)


def _render_translation_report(r: dict) -> None:
    if r.get("summary"):
        st.markdown("##### 📝 总评")
        st.info(r["summary"])

    miss = r.get("missing_points") or []
    if miss:
        st.markdown("##### 🔴 采分点遗漏")
        for m in miss:
            st.markdown(f"- :red[{m}]")

    ch = r.get("chinglish") or []
    if ch:
        st.markdown("##### ⚠️ 中式英语硬伤")
        for e in ch:
            if isinstance(e, dict):
                st.markdown(
                    f"- **原句**: _{e.get('sentence','')}_  \n"
                    f"  - 问题: {e.get('issue','')}  \n"
                    f"  - 建议: {e.get('fix','')}"
                )
            else:
                st.markdown(f"- :red[{e}]")

    ups = r.get("upgrades") or []
    if ups:
        st.markdown("##### 💎 高级替换建议")
        for u in ups:
            if isinstance(u, dict):
                st.markdown(
                    f"- ❌ `{u.get('from','')}` → ✅ **`{u.get('to','')}`**  \n"
                    f"  _{u.get('reason','')}_"
                )
            else:
                st.markdown(f"- {u}")

    if r.get("polished"):
        st.markdown("##### 🌟 润色版")
        st.success(r["polished"])


# ===========================================================================
# Sidebar
# ===========================================================================
def _render_sidebar() -> str:
    with st.sidebar:
        st.markdown("# 📱 CET 智胜")
        st.caption("V2.1 · 网页版 · 移动适配")

        st.markdown("---")
        st.markdown("### 📚 考试级别")
        new_level = st.radio(
            "切换",
            ["CET-4", "CET-6"],
            index=0 if st.session_state.level == "CET-4" else 1,
            label_visibility="collapsed",
        )
        if new_level != st.session_state.level:
            st.session_state.level = new_level
            st.rerun()

        st.markdown("---")
        st.markdown("### 🧭 功能板块")
        page = st.radio(
            "导航",
            ["📊 学霸看板",
             "📝 词汇板块",
             "🎲 背单词自测",
             "📰 阅读训练",
             "🎧 听力训练",
             "🤖 AI 批改官",
             "🟥 错题本"],
            label_visibility="collapsed",
        )

        st.markdown("---")
        with st.expander("🔑 API 配置"):
            base = st.text_input("Base URL",
                                  value=ai.config.get("base_url", ""))
            key = st.text_input("API Key",
                                 value=ai.config.get("api_key", ""),
                                 type="password")
            model = st.text_input("Model",
                                   value=ai.config.get("model", "gpt-3.5-turbo"))
            if st.button("💾 保存配置", use_container_width=True):
                ai.config["base_url"] = base.strip()
                ai.config["api_key"] = key.strip()
                ai.config["model"] = model.strip()
                ai.save_config()
                st.success("已保存 ✓")
                st.rerun()
        return page


# ===========================================================================
# Reading / Listening practice (shared renderer)
# ===========================================================================
def _safe_json_loads(raw: str | None, default):
    import json as _json
    if not raw:
        return default
    try:
        return _json.loads(raw)
    except Exception:
        return default


def _first_letter(text: str) -> str:
    """Pull 'A', 'B', 'C' or 'D' out of an option string like 'A. The man ...'.
    Returns empty string if no leading letter found."""
    if not text:
        return ""
    s = text.strip()
    if s and s[0].upper() in "ABCD":
        return s[0].upper()
    return ""


def _practice_item_label(item: dict, kind: str) -> str:
    """Human-readable picker label for an item."""
    yr = item.get("year") or "?"
    sess = item.get("session") or ""
    topic = item.get("topic_type") or ""
    if kind == "reading":
        title = (item.get("passage_title") or "Untitled").strip()
        return f"#{item.get('id')} · {yr} {sess} · {title[:40]}"
    else:  # listening
        section = (item.get("section") or "").strip()
        return f"#{item.get('id')} · {yr} {sess} · {section[:30]} {topic}".strip()


def _render_practice_session(kind: str) -> None:
    """Unified reading + listening practice flow.

    ``kind`` is ``'reading'`` or ``'listening'``. Reading shows the passage
    inline; listening shows an audio player and folds the transcript into
    an expander so the user can self-test before peeking.
    """
    level = st.session_state.level.replace("-", "")
    title = "📰 阅读训练" if kind == "reading" else "🎧 听力训练"
    st.markdown(f"## {title} · {level}")

    items = dm.list_reading(level) if kind == "reading" else dm.list_listening(level)
    if not items:
        st.warning(f"该级别暂无{('阅读' if kind=='reading' else '听力')}题目")
        return

    # ---- progress strip (cumulative + accuracy) ----
    stats = dm.practice_stats(level)
    attempts = stats[f"{kind}_attempts"]
    correct = stats[f"{kind}_correct"]
    rate = (correct / attempts * 100) if attempts else 0.0
    pcol1, pcol2, pcol3 = st.columns(3)
    pcol1.metric("累计答题", f"{attempts}")
    pcol2.metric("答对", f"{correct}")
    pcol3.metric("正确率", f"{rate:.1f}%")

    # ---- item picker ----
    idx = st.selectbox(
        "选一道题",
        list(range(len(items))),
        format_func=lambda i: _practice_item_label(items[i], kind),
        key=f"{kind}_pick",
    )
    item = items[idx]
    state_key = f"{kind}:{item['id']}"
    st.session_state.practice_state.setdefault(
        state_key, {"answers": {}, "submitted": False, "ai_reports": {}}
    )
    pstate = st.session_state.practice_state[state_key]

    # ---- material panel ----
    if kind == "reading":
        st.markdown(f"### {item.get('passage_title') or 'Passage'}")
        passage_html = (item.get("passage") or "").replace("\n", "<br>")
        st.markdown(
            f"<div style='line-height:1.85; padding:14px 16px; "
            f"background:#F8FAFC; border-radius:8px; border-left:4px solid #3B82F6;'>"
            f"{passage_html}</div>",
            unsafe_allow_html=True,
        )
    else:  # listening
        st.markdown(f"#### {item.get('section') or '听力'} · {item.get('topic_type') or ''}")
        audio_rel = item.get("audio_file") or ""
        audio_path = Path(audio_rel) if audio_rel else None
        if audio_path and audio_path.exists():
            try:
                st.audio(audio_path.read_bytes(), format="audio/mp3")
            except Exception as e:
                st.warning(f"音频加载失败:{e}")
        else:
            st.info("⚠️ 此题暂无音频文件,可参考下方原文练习")
        with st.expander("📜 听力原文 (做完再展开核对)", expanded=False):
            st.write(item.get("audio_script", "") or "(暂无原文)")

    # ---- questions ----
    questions = _safe_json_loads(item.get("questions"), default=[])
    correct_letters = parse_answer_letters(item.get("answers"))

    if not questions:
        st.error("题目数据缺失或损坏(questions 字段无法解析)")
        return

    st.markdown("---")
    st.markdown("### 📝 题目")
    for qi, q in enumerate(questions):
        st.markdown(f"**Q{qi+1}. {q.get('q','(题目缺失)')}**")
        opts = q.get("options", []) or []
        if not opts:
            st.caption("(无选项)")
            continue
        # Pre-select the previously stored answer if any, otherwise the first option.
        prev = pstate["answers"].get(qi)
        idx_default = opts.index(prev) if prev in opts else 0
        chosen = st.radio(
            label=f"q_{state_key}_{qi}",
            options=opts,
            index=idx_default,
            key=f"radio_{state_key}_{qi}",
            label_visibility="collapsed",
            disabled=pstate["submitted"],
        )
        pstate["answers"][qi] = chosen

    # ---- submit / feedback ----
    if not pstate["submitted"]:
        if st.button("✅ 提交本题答案", type="primary",
                      use_container_width=True,
                      key=f"submit_{state_key}"):
            for qi in range(len(questions)):
                ua = _first_letter(pstate["answers"].get(qi, ""))
                ca = correct_letters[qi] if qi < len(correct_letters) else ""
                try:
                    dm.record_practice_attempt(
                        item_type=kind, item_id=int(item["id"]),
                        level=level, q_index=qi,
                        user_answer=ua or None, correct_answer=ca,
                        source="web",
                    )
                except Exception as e:
                    st.error(f"持久化失败:{e}")
            pstate["submitted"] = True
            st.rerun()
        return

    # ---- post-submit: score banner + per-question feedback + AI explain ----
    n_total = len(questions)
    n_correct = 0
    for qi in range(n_total):
        ua = _first_letter(pstate["answers"].get(qi, ""))
        ca = correct_letters[qi] if qi < len(correct_letters) else ""
        if ua and ua == ca:
            n_correct += 1

    score_pct = (n_correct / n_total * 100) if n_total else 0
    if score_pct >= 80:
        st.success(f"🎉 得分:{n_correct} / {n_total}  ({score_pct:.0f}%) — 很棒!")
    elif score_pct >= 50:
        st.info(f"📊 得分:{n_correct} / {n_total}  ({score_pct:.0f}%) — 继续巩固")
    else:
        st.warning(f"💪 得分:{n_correct} / {n_total}  ({score_pct:.0f}%) — 再战一题")

    for qi, q in enumerate(questions):
        ua = _first_letter(pstate["answers"].get(qi, ""))
        ca = correct_letters[qi] if qi < len(correct_letters) else ""
        ok = bool(ua) and (ua == ca)
        color = "#10B981" if ok else "#EF4444"
        mark = "✅" if ok else "❌"
        st.markdown(
            f"<div style='border-left:4px solid {color}; padding:10px 14px; "
            f"margin:8px 0; background:{color}11; border-radius:6px;'>"
            f"<b>Q{qi+1}</b> &nbsp; 你的选择:<b>{ua or '(未选)'}</b> "
            f"&nbsp;·&nbsp; 正确答案:<b>{ca or '?'}</b> &nbsp;{mark}"
            f"</div>",
            unsafe_allow_html=True,
        )
        col_a, col_b = st.columns([1, 4])
        with col_a:
            if st.button("🧐 AI 讲解", key=f"explain_btn_{state_key}_{qi}",
                          use_container_width=True):
                with st.spinner("AI 老师正在分析此题..."):
                    try:
                        passage_text = (
                            item.get("passage") if kind == "reading"
                            else item.get("audio_script", "")
                        ) or ""
                        rpt = ai.explain_question(
                            kind=kind, passage=passage_text,
                            question=q.get("q", ""),
                            options=q.get("options", []) or [],
                            user_answer=ua, correct_answer=ca,
                            existing_analysis=item.get("analysis", "") or "",
                        )
                    except Exception as e:
                        st.error(f"AI 讲解失败:{e}")
                        rpt = None
                if rpt:
                    pstate["ai_reports"][qi] = rpt
                    st.rerun()

        rpt = pstate["ai_reports"].get(qi)
        if rpt:
            with col_b:
                if rpt.get("why_correct"):
                    st.info(f"✅ **正确解析** — {rpt['why_correct']}")
                if rpt.get("why_wrong"):
                    st.warning(f"❌ **你的选项错在哪** — {rpt['why_wrong']}")
                if rpt.get("trap"):
                    st.caption(f"⚠️ 出题陷阱:{rpt['trap']}")
                if rpt.get("key_phrases"):
                    st.caption(f"📌 考点短语:{rpt['key_phrases']}")

    # Original DB analysis (always available, complements AI)
    db_analysis = item.get("analysis", "") or ""
    if db_analysis:
        with st.expander("📒 官方/原始解析", expanded=False):
            st.write(db_analysis)

    st.markdown("---")
    rcol1, rcol2 = st.columns(2)
    with rcol1:
        if st.button("🔁 再做一次本题", key=f"reset_{state_key}",
                      use_container_width=True):
            st.session_state.practice_state.pop(state_key, None)
            st.rerun()
    with rcol2:
        if st.button("🎲 随机换一题", key=f"shuffle_{state_key}",
                      use_container_width=True):
            import random as _r
            others = [i for i in range(len(items)) if i != idx]
            if others:
                st.session_state[f"{kind}_pick"] = _r.choice(others)
                st.rerun()


def _render_reading_tab() -> None:
    _render_practice_session("reading")


def _render_listening_tab() -> None:
    _render_practice_session("listening")


def _render_wrongbook() -> None:
    """V2.2 错题本 — card list + always-on capture form."""
    level = st.session_state.level.replace("-", "")
    st.markdown(f"### 🟥 错题本 · {level}")
    rows = dm.list_wrong_book(level)

    # ----- ALWAYS-ON capture form (sits at the top so it's 1-tap to use) -----
    st.markdown("#### ➕ 一键捕捉生词到错题本")
    with st.form(key="catch_word_form", clear_on_submit=True):
        col1, col2 = st.columns([1, 2])
        with col1:
            new_w = st.text_input("英文单词 *", placeholder="ambiguous",
                                   label_visibility="collapsed")
        with col2:
            new_t = st.text_input("中文释义 (可选)", placeholder="模糊的",
                                   label_visibility="collapsed")
        submitted = st.form_submit_button("🟥 加入错题本",
                                          type="primary",
                                          use_container_width=True)
        if submitted:
            word = new_w.strip()
            if not word:
                st.error("请先输入英文单词")
            elif not word.replace(" ", "").replace("-", "").isalpha():
                st.error("单词格式无效 (只接受字母)")
            else:
                try:
                    row_id, created = dm.add_word_to_wrong_book(
                        word.lower(), level=level,
                        translation=new_t.strip(),
                        source="web_catch",
                    )
                    try:
                        dm.save_ai_catch_log(
                            section="web", level=level,
                            word=word.lower(), source_id=row_id,
                        )
                    except Exception:
                        pass  # dashboard counter is best-effort
                except Exception as e:
                    st.error(f"写入失败: {e}")
                else:
                    verb = "新建入错题本" if created else "已在错题本 (错题+1)"
                    st.success(f"✓ {word.lower()}  {verb}")
                    st.rerun()

    st.markdown("---")

    # ----- Empty state -----
    if not rows:
        st.info("🎉 错题本为空!继续保持!遇到不会的词在上面的输入框里一键加进来即可。")
        return

    # ----- Summary header -----
    n = len(rows)
    st.markdown(f"#### 当前错题 · 共 {n} 个")
    # sort by wrong_count desc so the worst-offenders bubble up
    rows_sorted = sorted(rows, key=lambda r: -(int(r.get("wrong_count", 0) or 0)))

    # ----- Card list -----
    for r in rows_sorted:
        word = r.get("word", "")
        trans = r.get("translation", "") or "(暂无中文)"
        wc = int(r.get("wrong_count", 0) or 0)
        last = str(r.get("last_seen_at", "") or "")
        # heat color
        if wc >= 3:
            border, badge = "#EF4444", "🔴 重点"
        elif wc >= 1:
            border, badge = "#F59E0B", "🟡 待巩固"
        else:
            border, badge = "#10B981", "🟢 稳定"
        with st.container():
            st.markdown(
                f"""
                <div style="
                    border-left: 4px solid {border};
                    background: linear-gradient(135deg, {border}11 0%, {border}03 100%);
                    border-radius: 8px;
                    padding: 12px 16px;
                    margin-bottom: 8px;
                ">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div>
                            <span style="font-size:20px; font-weight:700; color:#0F172A;">{word}</span>
                            <span style="font-size:14px; color:#6B7280; margin-left:8px;">{trans}</span>
                        </div>
                        <div style="font-size:12px; color:#6B7280;">{badge} · 错 {wc} 次</div>
                    </div>
                    <div style="font-size:11px; color:#9CA3AF; margin-top:4px;">
                        最近出错: {last if last else "(无记录)"}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            # Action row: mark-correct (= remove from wrong book)
            col_a, col_b = st.columns([1, 3])
            with col_a:
                if st.button(f"✅ 我会了", key=f"fix_{r.get('id', word)}_{wc}",
                              use_container_width=True):
                    try:
                        dm.record_correct(r["id"])
                    except Exception:
                        pass
                    st.toast(f"✓ {word} 已标记为会了")
                    st.rerun()
            with col_b:
                st.caption("点击后该词从错题本移除(并写入 consecutive_correct)")


# ===========================================================================
# Main
# ===========================================================================
def main() -> None:
    page = _render_sidebar()

    if page.startswith("📊"):
        _render_dashboard()
    elif page.startswith("📝"):
        _render_vocabulary_tab()
    elif page.startswith("🎲"):
        _render_quiz_tab()
    elif page.startswith("📰"):
        _render_reading_tab()
    elif page.startswith("🎧"):
        _render_listening_tab()
    elif page.startswith("🤖"):
        _render_ai_grader()
    elif page.startswith("🟥"):
        _render_wrongbook()
    else:
        _render_dashboard()

    st.markdown("---")
    st.caption("© CET 智胜 V2.1 · 网页版 · 基于 Streamlit + 桌面版数据/AI 复用")


if __name__ == "__main__":
    main()
