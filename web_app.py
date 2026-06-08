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

# Editorial Notebook design system. Loads CSS, helpers for hero /
# stat-sheet / chapter index. See web_ui.py for the design tokens.
import web_ui  # noqa: E402

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
    # Legacy single-question state, kept for backward compat with the
    # old "抽一题 → 答" flow. New code mostly uses quiz_current + the
    # quiz_session counters below.
    st.session_state.quiz_state = None
# ----- Multi-question "session" state (the "本轮测试" flow) -----
# quiz_active   -> True once "开始测试" pressed; gates the UI
# quiz_session  -> running totals for the current session
#                  {"planned": N, "attempted": N, "correct": N, "wrong": N}
# quiz_current  -> the question being displayed right now (a dict
#                  shaped like the old quiz_state) OR None if between
#                  questions; pre-fetched before rerun so the next
#                  paint always has something to show
if "quiz_active" not in st.session_state:
    st.session_state.quiz_active = False
if "quiz_session" not in st.session_state:
    st.session_state.quiz_session = None
if "quiz_current" not in st.session_state:
    st.session_state.quiz_current = None
if "practice_state" not in st.session_state:
    # One sub-dict per practice item, keyed f"{kind}:{item_id}".
    # Shape: {"answers": {q_index: option_text}, "submitted": bool,
    #         "ai_reports": {q_index: dict}}
    st.session_state.practice_state = {}
if "show_detail_dialog" not in st.session_state:
    st.session_state.show_detail_dialog = False
if "detail_word" not in st.session_state:
    st.session_state.detail_word = None
# Flow-control state for "previous / next" inside the detail dialog.
# We store IDs only (not full dicts) because the filtered list can hold
# 1000+ words and storing dicts would bloat the session.
if "current_words_ids" not in st.session_state:
    st.session_state.current_words_ids = []   # list[int]
if "current_word_index" not in st.session_state:
    st.session_state.current_word_index = 0


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
    """V3.0 学霸看板 — Editorial Notebook aesthetic.

    The data is the same; the visual language is that of a
    1920s-illustrated Chinese-English language primer. Big Playfair
    numerals, cinnabar-red accents, paper-edge borders, Roman
    numerals for section labels. Avoids the "AI dashboard" gradient
    soup entirely.
    """
    level = st.session_state.level.replace("-", "")
    stats = dm.dashboard_stats(level=level)

    # ----- Hero header (editorial top-of-page) -----
    web_ui.editorial_hero(level, stats["total_words"])

    # ----- Section break rule -----
    web_ui.editorial_rule("I · At a Glance")

    # ----- 4 stat tiles as a 1920s accounting-book ledger -----
    mastery_pct = (stats['mastered'] / max(1, stats['total_words']) * 100)
    ai_total = stats['ai_essay_grades'] + stats['ai_trans_grades']
    practice_total = stats['practice_reading'] + stats['practice_listening']
    web_ui.stat_sheet([
        {
            "no": "I",
            "value": stats['mastered'],
            "suffix": f" / {stats['total_words']:,}",
            "label": "已掌握词汇",
            "delta": f"({mastery_pct:.1f}% of the corpus)",
        },
        {
            "no": "II",
            "value": stats['wrong_book'],
            "label": "错题本待攻坚",
            "delta": "点击 🟥 错题本 反复练习",
            "delta_negative": True,
        },
        {
            "no": "III",
            "value": practice_total,
            "label": "刷题总量",
            "delta": f"阅读 {stats['practice_reading']} · 听力 {stats['practice_listening']}",
        },
        {
            "no": "IV",
            "value": ai_total,
            "label": "AI 批改次数",
            "delta": f"写作 {stats['ai_essay_grades']} · 翻译 {stats['ai_trans_grades']}",
        },
    ])

    # ----- Section break + secondary content -----
    web_ui.editorial_rule("II · Today's Editorial")

    # ----- Pull-quote + DB info in two paper cards -----
    left, right = st.columns([2, 1])
    with left:
        import datetime as _dt
        quote = random.choice(web_ui.QUOTES)
        st.markdown(
            f'<div class="paper-card">'
            f'<div class="editorial-no" style="margin-bottom:8px;">DAILY · '
            f'{_dt.date.today().strftime("%A %d %B").upper()}</div>'
            f'<p style="font-family:Georgia, \'Source Serif 4\',serif;'
            f'         font-size:22px; line-height:1.55; color:var(--ink); '
            f'         font-style:italic; margin:0;">'
            f'&ldquo;{quote}&rdquo;'
            f'</p>'
            f'<div style="margin-top:18px; font-size:13px; color:var(--ink-soft); '
            f'             font-style:italic;">— from the editor&apos;s desk</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with right:
        st.markdown(
            f'<div class="paper-card accent-cinnabar">'
            f'<div class="editorial-no" style="margin-bottom:6px;">COLOPHON</div>'
            f'<div style="font-family:{web_ui.FONT_BODY}; font-size:14px; '
            f'              line-height:1.65; color:var(--ink);">'
            f'<p style="margin:0 0 8px 0;">A working study system for '
            f'Chinese undergraduates sitting the College English Test, '
            f'first written in 2026. Backed by ten years of paper '
            f'archives and a small, well-trained language model.</p>'
            f'<p style="margin:0; font-size:12px; color:var(--ink-soft);">'
            f'<em>当前级别</em>: <strong style="color:var(--cinnabar);">'
            f'{st.session_state.level}</strong><br>'
            f'<em>主库路径</em>: <code>{dm.db_path}</code><br>'
            f'<em>词库总量</em>: {stats["total_words"]:,} 词'
            f'</p>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ----- Section break + the four quick links as a chapter index -----
    web_ui.editorial_rule("III · Today's Programme")

    nav_items = [
        ("II", "Vocabulary",   "词汇板块",       "vocab"),
        ("III", "Self-Test",   "背单词自测",     "quiz"),
        ("IV",  "Reading",     "阅读训练",       "reading"),
        ("V",   "Listening",   "听力训练",       "listening"),
        ("VI",  "AI Grader",   "AI 写作/翻译批改",  "grader"),
        ("VII", "Wrong Book",  "错题本",         "wrong"),
    ]
    # Render as 3-column paper-card grid
    cols = st.columns(3)
    for i, (no, en, zh, _key) in enumerate(nav_items):
        with cols[i % 3]:
            st.markdown(
                f'<div class="paper-card" style="padding:16px 20px;">'
                f'<div class="editorial-no">Chapter {no}</div>'
                f'<div style="font-family:{web_ui.FONT_DISPLAY}; font-size:22px; '
                f'              font-weight:700; color:var(--ink); margin:4px 0 2px 0; '
                f'              line-height:1.15;">{en}</div>'
                f'<div style="font-family:{web_ui.FONT_BODY}; font-size:13px; '
                f'              color:var(--cinnabar); font-style:italic;">{zh}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ----- Refresh button (kept for compatibility) -----
    st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)
    if st.button("🔄 Refresh data", use_container_width=True, key="dash_refresh"):
        st.cache_resource.clear()
        st.rerun()


# ===========================================================================
# Vocabulary + Quiz
# ===========================================================================
def _pick_quiz_word(level: str, source: str = "all") -> dict | None:
    """Pick one random word from a filtered pool.

    ``source`` values:
      - "all"     -> dm.list_vocabulary(level, min_star=1)
      - "mastered"-> dm.list_mastered(level)
      - "wrong"   -> dm.list_wrong_book(level)
    Returns ``None`` if the pool is empty.
    """
    import random as _r
    if source == "mastered":
        pool = dm.list_mastered(level)
    elif source == "wrong":
        pool = dm.list_wrong_book(level)
    else:  # "all" or any unknown value
        pool = dm.list_vocabulary(level, min_star=1)
    if not pool:
        return None
    return _r.choice(pool)


def _norm(s: str) -> str:
    """Normalize a string for loose comparison: lowercased, whitespace
    collapsed, full-width and half-width digits/punctuation brought
    closer together so 'cat,' and 'cat' match."""
    import re as _re
    if not s:
        return ""
    s = s.strip().lower()
    # collapse runs of whitespace
    s = _re.sub(r"\s+", " ", s)
    return s


def _stem_english(word: str) -> str:
    """Loose English stemmer — peels off a few common inflection
    suffixes so 'benefit' / 'benefits' / 'benefited' all count as a
    match. Deliberately conservative; we never want false positives."""
    if not word:
        return ""
    w = word.strip().lower()
    for suffix in ("ies", "ied", "ing", "ed", "es", "s", "'s"):
        if w.endswith(suffix) and len(w) > len(suffix) + 2:
            w = w[: -len(suffix)]
            break
    return w


def _judge_quiz_answer(user_input: str, answer: str, direction: str) -> bool:
    """True = user got it right. Pure function so the UI just calls
    this once and the DB-write side effect is the only thing outside
    its scope.

    Rules:
      * 英 → 中: any token in the user's answer (split on whitespace
        and Chinese punctuation) appears as a substring of ``answer``,
        OR the full normalized user string is contained in ``answer``.
        The substring rule lets "相同" pass for "adj.相似,相同".
      * 中 → 英: exact match on normalized strings, with one fallback
        — if the user's stem matches the answer's stem, accept it.
        No full substring because English single tokens rarely overlap
        that way.
    """
    if not user_input or not answer:
        return False
    if direction == "英 → 中":
        user_norm = _norm(user_input)
        ans_norm = _norm(answer)
        if not user_norm or not ans_norm:
            return False
        # Fast path: full string contained (catches '相同' → '相似,相同')
        if user_norm in ans_norm:
            return True
        # Token path: split user input on whitespace + common Chinese
        # delimiters, accept if any single token appears in the answer.
        import re as _re
        tokens = _re.split(r"[\s,，;；、]+", user_norm)
        tokens = [t for t in tokens if t]
        return any(tok and tok in ans_norm for tok in tokens)

    # 中 → 英
    user_norm = _norm(user_input)
    ans_norm = _norm(answer)
    if user_norm == ans_norm:
        return True
    # Stem fallback
    if _stem_english(user_norm) and _stem_english(user_norm) == _stem_english(ans_norm):
        return True
    return False


def _quiz_pool_size(level: str, source: str) -> int:
    """Cheap count of the current quiz pool (no row copy)."""
    if source == "mastered":
        return dm.count_mastered(level)
    if source == "wrong":
        return dm.count_wrong(level)
    # "all" — we don't have count_vocabulary, so reuse list length.
    # For the current ~5000-row table this is fine.
    return len(dm.list_vocabulary(level, min_star=1))


def _render_vocabulary_tab() -> None:
    level = st.session_state.level.replace("-", "")
    st.markdown(f"### 📝 词汇板块 · {level}")

    # NOTE: We deliberately do NOT call
    #   st.markdown(_VOCAB_CARD_CSS, unsafe_allow_html=True)
    # at the top of this page anymore. The <style> body contains
    # @keyframes and ::before pseudo-element rules that, when streamlit
    # renders them into the page-level React tree, can confuse React's
    # reconciler — it ends up trying to removeChild on a node that
    # belongs to a *different* React component, throwing the same
    # NotFoundError we used to see for <svg>. We now keep the CSS
    # entirely inside per-card iframes (see _components.html below),
    # where Streamlit never touches it.

    # ---- filter row ----
    cols = st.columns([2, 2, 1])
    search = cols[0].text_input("🔍 搜索单词 / 中文", "")
    star_labels = ["1⭐", "2⭐", "3⭐", "4⭐", "5⭐"]
    selected_star_labels = cols[1].multiselect(
        "星级 (多选)", star_labels,
        default=["4⭐", "5⭐"],
        help="留空 = 全部星级",
        key="vocab_stars",
    )
    only_wrong = cols[2].checkbox("只看错题本", False)

    # Convert "4⭐" -> 4. Empty selection means "all stars".
    selected_stars: set[int] = {
        int(s.replace("⭐", "")) for s in selected_star_labels
    }

    # ---- query (SQL floor + Python exact-set filter) ----
    # We push the lowest selected star into SQL as min_star so the
    # query doesn't drag back rows we'll throw away anyway. The exact
    # set filter runs in Python afterwards.
    sql_min = min(selected_stars) if selected_stars else 1
    try:
        words = dm.list_vocabulary(
            level, min_star=sql_min,
            search=search.strip() or None,
        )
    except Exception as e:
        st.error(f"查询失败: {e}")
        return

    # Hard star filter — this is the line you wanted: only keep words
    # whose star_rating is in the selected set. Empty set = no filter.
    if selected_stars:
        words = [
            w for w in words
            if int(w.get("star_rating", 0) or 0) in selected_stars
        ]

    if only_wrong:
        wrong_words = {w["word"] for w in dm.list_wrong_book(level)}
        words = [w for w in words if w["word"] in wrong_words]

    st.caption(
        f"共 {len(words)} 个词" +
        (f" · 星级:{' '.join(selected_star_labels)}"
         if selected_star_labels else " · 全部星级")
    )

    if not words:
        st.warning("没有匹配的单词。请调整筛选条件。")
        return

    # ---- expose the FILTERED word list to the dialog flow ----
    # The dialog's prev/next buttons walk this list, so it must mirror
    # whatever the user currently sees in the grid (search + star filter
    # + wrong-book toggle all applied). Stored as IDs to keep session
    # state lean. Updated every rerun, which means if the user changes
    # filters while the dialog is open, the next "next" click jumps to
    # the new list — acceptable, since changing filters implies they
    # want to re-scope their study.
    st.session_state.current_words_ids = [int(w["id"]) for w in words]

    # ---- pagination (smaller pages because cards are taller than rows) ----
    PAGE = 12
    if "vocab_page" not in st.session_state:
        st.session_state.vocab_page = 0
    max_page = max(0, (len(words) - 1) // PAGE)
    if st.session_state.vocab_page > max_page:
        st.session_state.vocab_page = 0
    page = st.session_state.vocab_page
    slice_ = words[page * PAGE: (page + 1) * PAGE]

    # ---- 3-column card grid ----
    COLS_PER_ROW = 3
    for row_start in range(0, len(slice_), COLS_PER_ROW):
        row = slice_[row_start: row_start + COLS_PER_ROW]
        cells = st.columns(COLS_PER_ROW, gap="medium")
        for cell, w in zip(cells, row):
            with cell:
                # Use components.html (iframe sandbox) instead of
                # st.markdown(unsafe_allow_html=True). The latter runs
                # the HTML through React's reconciler, which HTML-
                # escapes <svg> tags and triggers a downstream
                # NotFoundError when the DOM is re-rendered. The
                # iframe approach keeps the SVG markup completely
                # outside Streamlit's React tree.
                # Plain st.markdown(unsafe_*) — safe now that the
                # HTML body contains no <svg> tags, only <div> and
                # <span> with inline style. React's reconciler
                # handles these without throwing.
                st.markdown(
                    _VOCAB_CARD_CSS
                    + f"<div class='vocab-card-wrap'>{_render_vocab_card_html(w)}</div>",
                    unsafe_allow_html=True,
                )
                # ---- card action row: deep-dive + mastery toggle ----
                # Both buttons must be real st.button (HTML can't carry a
                # callback). Detail is primary action, mastery is secondary.
                a, b = st.columns([3, 2], gap="small")
                with a:
                    if st.button("🔍 深度背诵",
                                  key=f"detail_{w['id']}_{page}",
                                  type="primary",
                                  use_container_width=True):
                        # Jump the dialog to THIS word — find its index
                        # in the filtered list. Falls back to 0 if for
                        # some reason it isn't there (shouldn't happen).
                        try:
                            global_idx = st.session_state.current_words_ids.index(int(w["id"]))
                        except ValueError:
                            global_idx = 0
                        st.session_state.current_word_index = global_idx
                        st.session_state.detail_word = dict(w)
                        st.session_state.show_detail_dialog = True
                        st.rerun()
                with b:
                    mastered = bool(w.get("mastered"))
                    btn_label = "↩️" if mastered else "✅"
                    if st.button(btn_label,
                                  key=f"master_{w['id']}_{page}",
                                  use_container_width=True,
                                  help="取消掌握" if mastered
                                       else "标记已掌握"):
                        dm.toggle_mastered(w["id"])
                        st.rerun()

    # ---- open the detail dialog if a card requested it this rerun ----
    # NOTE: we do NOT clear show_detail_dialog here. The dialog manages
    # its own lifecycle — prev/next buttons and the mastery toggle rerun
    # the page but keep the flag True so the modal stays open. Only the
    # explicit close button flips it back off.
    if st.session_state.get("show_detail_dialog"):
        _show_word_detail(st.session_state.detail_word)

    # ---- pagination ----
    st.markdown("---")
    pcol1, pcol2, pcol3 = st.columns([1, 2, 1])
    with pcol1:
        if st.button("◀ 上一页", disabled=page == 0, use_container_width=True,
                      key="vocab_prev"):
            st.session_state.vocab_page = max(0, page - 1)
            st.rerun()
    with pcol2:
        st.markdown(
            f"<center style='line-height:38px;'>第 "
            f"<b>{page + 1}</b> / <b>{max_page + 1}</b> 页 · "
            f"每页 {PAGE} 张</center>",
            unsafe_allow_html=True,
        )
    with pcol3:
        if st.button("下一页 ▶", disabled=page >= max_page,
                      use_container_width=True, key="vocab_next"):
            st.session_state.vocab_page = min(max_page, page + 1)
            st.rerun()


# ---------------------------------------------------------------------------
# SVG icon library — used in place of emoji everywhere in the UI.
# Each function returns a self-contained <svg> string you can drop
# inside a span, a div, or a button. Stroke-based icons; no external
# font dependency, no colour-font fallbacks, render identically on
# Windows / macOS / iOS / Android.
#
# All icons are 1em x 1em by default so they inherit the surrounding
# text size. Pass ``size="32"`` to override.
# ---------------------------------------------------------------------------
def _svg_attrs(size: str = "1em") -> str:
    return (f'xmlns="http://www.w3.org/2000/svg" width="{size}" '
            f'height="{size}" viewBox="0 0 24 24" fill="none" '
            f'stroke="currentColor" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round"')


def _svg_star_filled(size: str = "1em") -> str:
    """Solid five-point star (Material Icons 'star')."""
    return (f'<svg {_svg_attrs(size)} fill="currentColor" stroke="none">'
            f'<path d="M12 2l2.39 6.95H22l-5.78 4.18 2.21 6.93L12 16.27 '
            f'5.57 13.06l2.21-6.93L2 8.95h7.61L12 2z"/>'
            f'</svg>')


def _svg_star_outline(size: str = "1em") -> str:
    """Hollow five-point star for 'un-earned' ratings."""
    return (f'<svg {_svg_attrs(size)} fill="none" stroke="currentColor" '
            f'stroke-width="1.6">'
            f'<path d="M12 4.5l1.7 4.95h5.15l-4.17 3.02 1.6 4.92L12 14.7 '
            f'l-4.28 2.69 1.6-4.92L5.15 9.45h5.15L12 4.5z"/>'
            f'</svg>')


def _svg_check(size: str = "1em") -> str:
    """Stroke-based checkmark inside a circle."""
    return (f'<svg {_svg_attrs(size)}>'
            f'<circle cx="12" cy="12" r="10" fill="currentColor" stroke="none"/>'
            f'<path d="M7 12.5l3.2 3.2L17 9" stroke="white" stroke-width="2.4"/>'
            f'</svg>')


def _svg_cross(size: str = "1em") -> str:
    """Stroke-based X inside a circle."""
    return (f'<svg {_svg_attrs(size)}>'
            f'<circle cx="12" cy="12" r="10" fill="currentColor" stroke="none"/>'
            f'<path d="M8.5 8.5l7 7M15.5 8.5l-7 7" stroke="white" stroke-width="2.4"/>'
            f'</svg>')


def _svg_info(size: str = "1em") -> str:
    """'i' inside a circle — for the 'skipped' / neutral state."""
    return (f'<svg {_svg_attrs(size)}>'
            f'<circle cx="12" cy="12" r="10" fill="currentColor" stroke="none"/>'
            f'<path d="M12 8v.5M12 11v6" stroke="white" stroke-width="2.4"/>'
            f'</svg>')


def _svg_sparkles(size: str = "1em") -> str:
    """Four-pointed star burst — used for the AI-generate button."""
    return (f'<svg {_svg_attrs(size)} fill="currentColor" stroke="none">'
            f'<path d="M12 2l1.6 6.4L20 10l-6.4 1.6L12 18l-1.6-6.4L4 10l6.4-1.6L12 2z"/>'
            f'<path d="M19 16l.7 2.3L22 19l-2.3.7L19 22l-.7-2.3L16 19l2.3-.7L19 16z"/>'
            f'</svg>')


def _svg_dice(size: str = "1em") -> str:
    """Six-dot die — the self-test tab icon."""
    return (f'<svg {_svg_attrs(size)} fill="none" stroke="currentColor" '
            f'stroke-width="1.8">'
            f'<rect x="4" y="4" width="16" height="16" rx="3"/>'
            f'<circle cx="8" cy="8" r="1" fill="currentColor"/>'
            f'<circle cx="16" cy="8" r="1" fill="currentColor"/>'
            f'<circle cx="8" cy="16" r="1" fill="currentColor"/>'
            f'<circle cx="16" cy="16" r="1" fill="currentColor"/>'
            f'<circle cx="12" cy="12" r="1" fill="currentColor"/>'
            f'<circle cx="8" cy="12" r="1" fill="currentColor"/>'
            f'</svg>')


def _svg_headphones(size: str = "1em") -> str:
    """Headphones — listening tab icon."""
    return (f'<svg {_svg_attrs(size)}>'
            f'<path d="M4 14v-2a8 8 0 0116 0v2"/>'
            f'<rect x="3" y="14" width="4" height="6" rx="1.5" fill="currentColor" stroke="none"/>'
            f'<rect x="17" y="14" width="4" height="6" rx="1.5" fill="currentColor" stroke="none"/>'
            f'</svg>')


def _svg_book_open(size: str = "1em") -> str:
    """Open book — reading tab icon."""
    return (f'<svg {_svg_attrs(size)}>'
            f'<path d="M3 5h6a3 3 0 013 3v12a2 2 0 00-2-2H3V5z"/>'
            f'<path d="M21 5h-6a3 3 0 00-3 3v12a2 2 0 012-2h7V5z"/>'
            f'</svg>')


def _svg_search(size: str = "1em") -> str:
    """Magnifying glass — deep-dive button."""
    return (f'<svg {_svg_attrs(size)}>'
            f'<circle cx="11" cy="11" r="7"/>'
            f'<path d="M20 20l-3.5-3.5"/>'
            f'</svg>')


def _svg_target(size: str = "1em") -> str:
    """Bullseye — quiz 'draw a question' button."""
    return (f'<svg {_svg_attrs(size)}>'
            f'<circle cx="12" cy="12" r="9"/>'
            f'<circle cx="12" cy="12" r="5"/>'
            f'<circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none"/>'
            f'</svg>')


def _svg_trophy(size: str = "1em") -> str:
    """Trophy — quiz session result page."""
    return (f'<svg {_svg_attrs(size)} fill="none" stroke="currentColor" '
            f'stroke-width="1.8">'
            f'<path d="M8 4h8v4a4 4 0 11-8 0V4z"/>'
            f'<path d="M4 4h4v3a3 3 0 01-3 3H4V4zM20 4h-4v3a3 3 0 003 3h1V4z"/>'
            f'<path d="M9 14h6l-.5 5h-5L9 14z"/>'
            f'</svg>')


def _svg_arrow_right(size: str = "1em") -> str:
    """Right-pointing arrow — 'next question' button."""
    return (f'<svg {_svg_attrs(size)}>'
            f'<path d="M5 12h14M13 6l6 6-6 6"/>'
            f'</svg>')


def _svg_arrow_left(size: str = "1em") -> str:
    return (f'<svg {_svg_attrs(size)}>'
            f'<path d="M19 12H5M11 6l-6 6 6 6"/>'
            f'</svg>')


def _svg_pin(size: str = "1em") -> str:
    """Pushpin — 'topic' / 'requirements' label."""
    return (f'<svg {_svg_attrs(size)} fill="currentColor" stroke="none">'
            f'<path d="M14 4l6 6-3 1-2 5-3-3-5 5-2-2 5-5-3-3 5-2 1-3z"/>'
            f'</svg>')


def _svg_palette(size: str = "1em") -> str:
    """AI grader icon."""
    return (f'<svg {_svg_attrs(size)} fill="none" stroke="currentColor" '
            f'stroke-width="1.7">'
            f'<path d="M12 3a9 9 0 100 18c1 0 2-.5 2-1.5 0-1-.5-1.5-1-2-.5-.5-1-1-1-2 0-1.5 1-2.5 3-2.5h2a4 4 0 004-4c0-3.5-4-6-9-6z"/>'
            f'<circle cx="7.5" cy="10" r="1.2" fill="currentColor"/>'
            f'<circle cx="11" cy="6.8" r="1.2" fill="currentColor"/>'
            f'<circle cx="15" cy="9" r="1.2" fill="currentColor"/>'
            f'<circle cx="17" cy="13" r="1.2" fill="currentColor"/>'
            f'</svg>')


def _svg_bar_chart(size: str = "1em") -> str:
    """Bar chart — dashboard tab icon."""
    return (f'<svg {_svg_attrs(size)} fill="currentColor" stroke="none">'
            f'<rect x="4" y="13" width="3" height="7" rx="0.5"/>'
            f'<rect x="10" y="9" width="3" height="11" rx="0.5"/>'
            f'<rect x="16" y="5" width="3" height="15" rx="0.5"/>'
            f'</svg>')


def _svg_flag(size: str = "1em") -> str:
    """End session button."""
    return (f'<svg {_svg_attrs(size)} fill="none" stroke="currentColor" '
            f'stroke-width="1.8">'
            f'<path d="M5 21V4h11l-2 4 2 4H5"/>'
            f'</svg>')


def _svg_flame(size: str = "1em") -> str:
    """Difficulty / 'hot' indicator."""
    return (f'<svg {_svg_attrs(size)} fill="currentColor" stroke="none">'
            f'<path d="M12 3s5 5 5 10a5 5 0 11-10 0c0-2 1-3 2-4 0 1 1 2 2 2 0-2-1-3 1-8z"/>'
            f'</svg>')


def _svg_close(size: str = "1em") -> str:
    """X-mark — close dialog / modal button."""
    return (f'<svg {_svg_attrs(size)}>'
            f'<path d="M6 6l12 12M18 6L6 18"/>'
            f'</svg>')


def _svg_speaker(size: str = "1em") -> str:
    """Speaker / pronunciation — used in the detail dialog."""
    return (f'<svg {_svg_attrs(size)} fill="none" stroke="currentColor" '
            f'stroke-width="1.7">'
            f'<path d="M3 10v4h4l5 4V6L7 10H3z"/>'
            f'<path d="M15 9a4 4 0 010 6" />'
            f'<path d="M18 6a8 8 0 010 12" />'
            f'</svg>')


# Reusable short codes — old emoji names mapped to SVG renderers.
# Keeps the rest of the codebase readable when we swap one for the other.
_ICON = {
    "star_gold": _svg_star_filled,
    "star_outline": _svg_star_outline,
    "check": _svg_check,
    "cross": _svg_cross,
    "info": _svg_info,
    "sparkles": _svg_sparkles,
    "dice": _svg_dice,
    "headphones": _svg_headphones,
    "book_open": _svg_book_open,
    "search": _svg_search,
    "target": _svg_target,
    "trophy": _svg_trophy,
    "arrow_right": _svg_arrow_right,
    "arrow_left": _svg_arrow_left,
    "pin": _svg_pin,
    "palette": _svg_palette,
    "bar_chart": _svg_bar_chart,
    "flag": _svg_flag,
    "flame": _svg_flame,
    "close": _svg_close,
    "speaker": _svg_speaker,
}


def _icon(name: str, size: str = "1em", css_class: str = "") -> str:
    """Convenience: get a wrapped <span class="vocab-icon"> with the SVG."""
    svg = _ICON[name](size) if name in _ICON else f"?"
    cls = f' class="vocab-icon {css_class}"' if css_class else ' class="vocab-icon"'
    return f'<span{cls}>{svg}</span>'


# ---------------------------------------------------------------------------
# Vocabulary card — HTML/CSS helpers
# ---------------------------------------------------------------------------
_VOCAB_CARD_CSS = """
<style>
.vocab-card {
    background: linear-gradient(155deg, #FFFFFF 0%, #F8FAFC 100%);
    border: 1px solid #E5E7EB;
    border-radius: 14px;
    padding: 16px 18px 14px 18px;
    margin-bottom: 6px;
    box-shadow: 0 2px 6px rgba(15, 23, 42, 0.06);
    min-height: 215px;
    display: flex;
    flex-direction: column;
    transition: box-shadow .15s ease, transform .15s ease;
}
.vocab-card:hover {
    box-shadow: 0 6px 18px rgba(59, 130, 246, 0.15);
    transform: translateY(-2px);
}
.vocab-card-head {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 4px;
}
.vocab-card-word {
    font-size: 22px;
    font-weight: 800;
    color: #0F172A;
    letter-spacing: 0.2px;
    word-break: break-word;
}
.vocab-card-stars {
    font-size: 16px;
    line-height: 1;
    letter-spacing: 1px;
    white-space: nowrap;
    margin-left: 8px;
}
.vocab-card-meta {
    font-size: 12px;
    color: #6B7280;
    margin-bottom: 8px;
    line-height: 1.3;
}
.vocab-card-pos {
    display: inline-block;
    background: #EDE9FE;
    color: #6D28D9;
    padding: 1px 7px;
    border-radius: 4px;
    font-weight: 600;
    margin-right: 6px;
    font-size: 11px;
}
.vocab-card-trans {
    font-size: 14px;
    color: #1F2937;
    line-height: 1.45;
    margin-bottom: 6px;
    flex: 0 0 auto;
}
.vocab-card-example {
    font-size: 12px;
    color: #64748B;
    font-style: italic;
    line-height: 1.5;
    background: #F1F5F9;
    border-left: 3px solid #94A3B8;
    padding: 6px 8px;
    border-radius: 4px;
    margin-bottom: 8px;
    /* clamp to 2 lines so cards keep an even height */
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    flex: 1 1 auto;
}
.vocab-card-foot {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: auto;
    padding-top: 6px;
    border-top: 1px dashed #E5E7EB;
}
.vocab-badge {
    font-size: 11px;
    padding: 3px 9px;
    border-radius: 999px;
    font-weight: 600;
    line-height: 1.1;
}
.vocab-badge-mastered {
    background: #DCFCE7;
    color: #166534;
    border: 1px solid #86EFAC;
}
.vocab-badge-wrong {
    background: #FEE2E2;
    color: #991B1B;
    border: 1px solid #FCA5A5;
}
.vocab-badge-new {
    background: #DBEAFE;
    color: #1E40AF;
    border: 1px solid #93C5FD;
}
.vocab-card-freq {
    font-size: 11px;
    color: #6B7280;
}
.vocab-card-freq b { color: #0F172A; font-weight: 700; }

/* ============================================================
   SVG-icon styling — replaces the old emoji glyphs.
   All <span class="vocab-icon"> inherit the surrounding text color
   via ``currentColor``, so we just control colour at the parent.
   ============================================================ */
.vocab-icon {
    display: inline-flex;
    align-items: center;
    vertical-align: -0.18em;
    line-height: 1;
    margin: 0 1px;
}
.vocab-icon svg {
    display: block;
}

/* The five star cells inside .vocab-card-stars */
.vocab-card-stars .vocab-icon {
    margin: 0 1.5px;
    transition: transform .15s ease;
}
.vocab-card-stars .vocab-icon.gold svg { color: #FFC107; }
.vocab-card-stars .vocab-icon.gray svg { color: #E5E7EB; }
.vocab-card:hover .vocab-card-stars .vocab-icon.gold {
    animation: starWiggle 1.6s ease-in-out infinite;
}

/* Subtle breathing / fade-in for status badges (▶ checkmark, ▶ cross) */
@keyframes badgePulse {
    0%, 100% { transform: scale(1);   opacity: 1;   }
    50%      { transform: scale(1.08); opacity: 0.9; }
}
@keyframes badgeFadeIn {
    from { transform: scale(0.7); opacity: 0; }
    to   { transform: scale(1);   opacity: 1;   }
}
@keyframes starWiggle {
    0%, 100% { transform: rotate(0deg)   scale(1);    }
    25%      { transform: rotate(-6deg)  scale(1.06); }
    75%      { transform: rotate(6deg)   scale(1.06); }
}
@keyframes bannerSlideIn {
    from { transform: translateY(-12px); opacity: 0; }
    to   { transform: translateY(0);     opacity: 1; }
}
@keyframes confettiBurst {
    0%   { transform: scale(0.4) rotate(0deg);   opacity: 0; }
    60%  { transform: scale(1.15) rotate(8deg);  opacity: 1; }
    100% { transform: scale(1)    rotate(0deg);  opacity: 1; }
}

/* Quiz banner (correct / wrong / skipped) — slide + glow */
.quiz-banner {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 16px 20px;
    border-radius: 12px;
    margin: 12px 0;
    font-size: 17px;
    font-weight: 600;
    animation: bannerSlideIn .35s cubic-bezier(.2, .9, .3, 1.1);
}
.quiz-banner .vocab-icon {
    width: 44px;
    height: 44px;
    flex-shrink: 0;
    animation: confettiBurst .55s cubic-bezier(.2, .9, .3, 1.2);
}
.quiz-banner.correct {
    background: linear-gradient(135deg, #DCFCE7 0%, #F0FDF4 100%);
    border-left: 5px solid #10B981;
    color: #065F46;
}
.quiz-banner.correct .vocab-icon svg { color: #10B981; }
.quiz-banner.wrong {
    background: linear-gradient(135deg, #FEE2E2 0%, #FEF2F2 100%);
    border-left: 5px solid #EF4444;
    color: #991B1B;
}
.quiz-banner.wrong .vocab-icon svg { color: #EF4444; }
.quiz-banner.skipped {
    background: linear-gradient(135deg, #FEF3C7 0%, #FFFBEB 100%);
    border-left: 5px solid #F59E0B;
    color: #92400E;
}
.quiz-banner.skipped .vocab-icon svg { color: #F59E0B; }

/* Badges — SVG icon is now embedded directly in the Python HTML
   string, NOT via CSS ::before mask-image. CSS mask-image data URLs
   were being mis-escaped by Streamlit's React rendering, throwing
   NotFoundError when the page re-rendered with a new badge. The
   in-Python approach is bulletproof. The badge still gets a subtle
   fade-in animation. */
.vocab-badge {
    animation: badgeFadeIn .35s ease-out;
}
.vocab-badge .vocab-icon {
    width: 0.95em;
    height: 0.95em;
    margin-right: 5px;
    vertical-align: -0.18em;
    color: currentColor;
}
.vocab-badge-mastered .vocab-icon {
    animation: badgePulse 2.4s ease-in-out infinite;
}
.vocab-badge-new .vocab-icon { color: #1E40AF; }

/* Banner big-symbol icon (Unicode glyphs in a styled span — no SVG) */
.vocab-banner-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    height: 44px;
    flex-shrink: 0;
    border-radius: 50%;
    font-size: 24px;
    font-weight: 700;
    color: white;
    background: currentColor;
    line-height: 1;
    text-indent: -1px;       /* optical centering */
    animation: confettiBurst .55s cubic-bezier(.2, .9, .3, 1.2);
}
.quiz-banner.correct .vocab-banner-icon { color: #10B981; }
.quiz-banner.wrong   .vocab-banner-icon { color: #EF4444; }
.quiz-banner.skipped .vocab-banner-icon { color: #F59E0B; }
</style>
"""


def _split_pos_from_translation(trans: str) -> tuple[str, str]:
    """Most rows store translation as e.g. 'adj.相似,相同' — the POS is
    glued to the front. Pull it off so we can render it as a pill.

    Returns (pos, body). If no recognizable POS is found, returns
    ('', original).
    """
    import re as _re
    if not trans:
        return "", ""
    m = _re.match(
        r"^\s*(adj|adv|n|v|vt|vi|prep|conj|pron|num|art|interj|aux)\.\s*",
        trans, _re.IGNORECASE,
    )
    if not m:
        return "", trans.strip()
    return m.group(1).lower() + ".", trans[m.end():].strip()


def _html_escape(text: str) -> str:
    """Minimal HTML escape so word/translation can't break the card."""
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _render_vocab_card_html(w: dict) -> str:
    """Build the full HTML string for one vocabulary card."""
    word = _html_escape(w.get("word", ""))
    phonetic = _html_escape(w.get("phonetic", "") or "[—]")
    star = max(0, min(5, int(w.get("star_rating", 0) or 0)))
    # SVG-rendered five-point stars. Gold ★ for earned, hollow ☆ for
    # un-earned. Each cell is a span.vocab-icon so the CSS animation
    # (starWiggle) can fire on hover. This replaces the old ★/☆
    # Unicode glyphs which had inconsistent colour on Windows.
    # Plain Unicode stars. CSS gold/gray can colour these via
    # inline spans (the chars are NOT emoji-font glyphs, so
    # `color: ...` works on Windows). No <svg>, no React escape risk.
    stars_html = (
        "<span style='color:#F59E0B'>" + ("★" * star) + "</span>"
        "<span style='color:#D1D5DB'>" + ("☆" * (5 - star)) + "</span>"
    )

    raw_trans = w.get("translation", "") or ""
    pos_inline, trans_body = _split_pos_from_translation(raw_trans)
    db_pos = (w.get("pos") or "").strip()
    pos = db_pos or pos_inline  # prefer the explicit pos column
    trans_html = _html_escape(trans_body or "(暂无中文释义)")

    example = (w.get("example_sentence") or "").strip()
    if example:
        # Highlight the word itself for quick visual anchor
        try:
            import re as _re
            ex_html = _re.sub(
                r"(?i)\b(" + _re.escape(w.get("word", "")) + r")\b",
                r"<b style='color:#1F2937'>\1</b>",
                _html_escape(example),
            )
        except Exception:
            ex_html = _html_escape(example)
        example_html = f"<div class='vocab-card-example'>“{ex_html}”</div>"
    else:
        example_html = ""

    pos_html = f"<span class='vocab-card-pos'>{_html_escape(pos)}</span>" if pos else ""

    mastered = bool(w.get("mastered"))
    wrong = int(w.get("wrong_count", 0) or 0)
    # Badge icons are inlined SVG (NOT CSS ::before with data-URL
    # masks, which Streamlit was mis-escaping → DOM insertBefore error).
    if mastered:
        badge_html = "<span class='vocab-badge vocab-badge-mastered'>✓ 已掌握</span>"
    elif wrong > 0:
        badge_html = f"<span class='vocab-badge vocab-badge-wrong'>✗ 错 {wrong} 次</span>"
    else:
        badge_html = "<span class='vocab-badge vocab-badge-new'>★ 新词</span>"

    freq = int(w.get("frequency", 0) or 0)

    return (
        f"<div class='vocab-card'>"
        f"  <div class='vocab-card-head'>"
        f"    <div class='vocab-card-word'>{word}</div>"
        f"    <div class='vocab-card-stars' title='{star} 星'>{stars_html}</div>"
        f"  </div>"
        f"  <div class='vocab-card-meta'>{pos_html}{phonetic}</div>"
        f"  <div class='vocab-card-trans'>{trans_html}</div>"
        f"  {example_html}"
        f"  <div class='vocab-card-foot'>"
        f"    {badge_html}"
        f"    <div class='vocab-card-freq'>频次 <b>{freq}</b></div>"
        f"  </div>"
        f"</div>"
    )


# ---------------------------------------------------------------------------
# Deep-study modal — opened by the 🔍 button on each vocab card
# ---------------------------------------------------------------------------
@st.dialog("🔍 深度背诵", width="large")
def _show_word_detail(w: dict) -> None:
    """Full-screen-feeling modal with high-density study info for one word.

    Flow control: walks ``st.session_state.current_words_ids`` using
    ``current_word_index``. Prev/Next buttons mutate the index and
    rerun — the dialog stays open (``show_detail_dialog`` flag persists)
    so the user can flip through the entire filtered list without
    closing the modal. Close button flips the flag off explicitly.
    """
    ids: list[int] = st.session_state.get("current_words_ids", []) or []
    idx: int = int(st.session_state.get("current_word_index", 0) or 0)
    total = len(ids)

    # Re-resolve the current word by index — this is the source of truth.
    # The ``w`` argument is only a fallback for the very first paint
    # before the index flow takes over.
    current = w
    if total > 0 and 0 <= idx < total:
        try:
            fresh = dm.get_word_by_id(ids[idx])
            if fresh:
                current = fresh
        except Exception:
            pass
    elif w:
        # Keep the originally-stashed word if the id list is somehow empty
        current = w

    if not current:
        st.error("数据加载失败,请关闭弹窗重试。")
        if st.button("关闭", use_container_width=True, key="dlg_close_err"):
            st.session_state.show_detail_dialog = False
            st.rerun()
        return

    word = current.get("word", "") or "(unknown)"
    phonetic = current.get("phonetic", "") or "[—]"
    raw_trans = current.get("translation", "") or ""
    pos_inline, trans_body = _split_pos_from_translation(raw_trans)
    db_pos = (current.get("pos") or "").strip()
    pos = db_pos or pos_inline
    star = max(0, min(5, int(current.get("star_rating", 0) or 0)))
    freq = int(current.get("frequency", 0) or 0)
    mastered = bool(current.get("mastered"))
    wrong = int(current.get("wrong_count", 0) or 0)
    example = (current.get("example_sentence") or "").strip()
    ex_trans = (current.get("example_translation") or "").strip()
    wid = int(current.get("id", 0) or 0)

    # ----- Progress strip (where am I in the list?) -----
    if total > 0:
        st.markdown(
            f"<div style='text-align:center; color:#6B7280; font-size:13px;"
            f"           margin-bottom:6px;'>"
            f"📍 第 <b style='color:#3B82F6'>{idx + 1}</b> / "
            f"{total} 个词 · 当前筛选范围</div>",
            unsafe_allow_html=True,
        )

    # ----- Hero: huge word + phonetic + speaker icon -----
    pos_pill = (
        f"<span style='display:inline-block;background:#EDE9FE;color:#6D28D9;"
        f"padding:2px 10px;border-radius:6px;font-size:14px;font-weight:600;"
        f"margin-right:10px;vertical-align:middle;'>{_html_escape(pos)}</span>"
        if pos else ""
    )
    st.markdown(
        f"<div style='text-align:center; padding:20px 8px 14px 8px;"
        f"background:linear-gradient(135deg,#EFF6FF 0%, #F8FAFC 100%);"
        f"border-radius:12px; margin-bottom:18px;'>"
        f"  <div style='font-size:48px; font-weight:800; color:#0F172A;"
        f"             letter-spacing:1px; line-height:1.1;'>{_html_escape(word)}</div>"
        f"  <div style='margin-top:10px; color:#475569;'>"
        f"    {pos_pill}"
        f"    <span style='font-size:18px;'>{_html_escape(phonetic)}</span>"
        f"    <span style='font-size:22px; margin-left:10px;"
        f"               cursor:default;' title='发音 (浏览器原生 TTS)'>🔊</span>"
        f"  </div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ----- Star + frequency + status -----
    s1, s2, s3 = st.columns(3)
    stars_solid = "★" * star
    stars_hollow = "☆" * (5 - star)
    s1.markdown(
        f"<div style='text-align:center;'>"
        f"  <div style='font-size:12px; color:#6B7280;'>考频星级</div>"
        f"  <div style='font-size:24px; line-height:1.2;'>"
        f"    <span style='color:#F59E0B;'>{stars_solid}</span>"
        f"    <span style='color:#D1D5DB;'>{stars_hollow}</span>"
        f"  </div>"
        f"  <div style='font-size:11px; color:#9CA3AF;'>{star}/5 星</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    s2.markdown(
        f"<div style='text-align:center;'>"
        f"  <div style='font-size:12px; color:#6B7280;'>真题出现频次</div>"
        f"  <div style='font-size:28px; font-weight:700; color:#DC2626;'>{freq}</div>"
        f"  <div style='font-size:11px; color:#9CA3AF;'>越高越要背</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    if mastered:
        status_color, status_text, status_hint = "#10B981", "✓ 已掌握", "继续保持!"
    elif wrong > 0:
        status_color, status_text, status_hint = "#EF4444", f"✗ 错 {wrong} 次", "重点攻坚"
    else:
        status_color, status_text, status_hint = "#3B82F6", "新词", "首次学习"
    s3.markdown(
        f"<div style='text-align:center;'>"
        f"  <div style='font-size:12px; color:#6B7280;'>掌握状态</div>"
        f"  <div style='font-size:20px; font-weight:700; color:{status_color};'>"
        f"    {status_text}</div>"
        f"  <div style='font-size:11px; color:#9CA3AF;'>{status_hint}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    # ----- Core meaning -----
    st.markdown("#### 📖 核心释义")
    if trans_body:
        st.success(f"### {trans_body}")
    else:
        st.info("(暂无中文释义,可在错题本里补充)")

    # ----- Real-exam example sentence + translation -----
    st.markdown("#### ✍️ 真题例句")
    if example:
        try:
            import re as _re
            ex_html = _re.sub(
                r"(?i)\b(" + _re.escape(word) + r")\b",
                r"<b style='color:#DC2626;background:#FEF3C7;padding:0 4px;"
                r"border-radius:3px;'>\1</b>",
                _html_escape(example),
            )
        except Exception:
            ex_html = _html_escape(example)
        st.markdown(
            f"<div style='font-size:18px; line-height:1.8; color:#1F2937;"
            f"           background:#FFFBEB; border-left:5px solid #F59E0B;"
            f"           padding:14px 18px; border-radius:8px;"
            f"           font-family:Georgia, \"Times New Roman\", serif;'>"
            f"“{ex_html}”</div>",
            unsafe_allow_html=True,
        )
        if ex_trans:
            st.markdown(
                f"<div style='font-size:15px; color:#475569;"
                f"           padding:10px 18px 4px 18px;'>"
                f"💡 {_html_escape(ex_trans)}</div>",
                unsafe_allow_html=True,
            )
    else:
        st.caption("此词暂无配套真题例句")

    tags = (current.get("tags") or "").strip()
    if tags:
        st.caption(f"📌 来源标签: {tags}")

    st.markdown("---")

    # ----- Navigation row: ◀ prev / mastery toggle / next ▶ -----
    # 4 columns so prev/next sit at the edges with the mastery and close
    # buttons in the middle — keeps thumbs at the corners on mobile.
    nav_prev, nav_master, nav_close, nav_next = st.columns([1, 2, 1, 1],
                                                            gap="small")

    with nav_prev:
        prev_disabled = total == 0 or idx <= 0
        if st.button("◀ 上一个",
                      use_container_width=True,
                      disabled=prev_disabled,
                      key=f"dlg_prev_{wid}_{idx}"):
            st.session_state.current_word_index = max(0, idx - 1)
            st.rerun()

    with nav_master:
        if mastered:
            if st.button("↩️  取消掌握",
                          type="secondary",
                          use_container_width=True,
                          key=f"dlg_master_{wid}_{idx}"):
                dm.toggle_mastered(wid)
                st.rerun()
        else:
            if st.button("✅  标记已掌握",
                          type="primary",
                          use_container_width=True,
                          key=f"dlg_master_{wid}_{idx}"):
                dm.toggle_mastered(wid)
                st.rerun()

    with nav_close:
        if st.button("关闭",
                      use_container_width=True,
                      key=f"dlg_close_{wid}_{idx}"):
            st.session_state.show_detail_dialog = False
            st.rerun()

    with nav_next:
        next_disabled = total == 0 or idx >= total - 1
        if st.button("下一个 ▶",
                      type="primary" if not next_disabled else "secondary",
                      use_container_width=True,
                      disabled=next_disabled,
                      key=f"dlg_next_{wid}_{idx}"):
            st.session_state.current_word_index = min(total - 1, idx + 1)
            st.rerun()


def _render_quiz_tab() -> None:
    """Self-test page state machine.

    Four visible states, gated on (quiz_active, quiz_current, ended_at):
      * session ended    -> _render_quiz_result
      * quiz_current set -> _render_quiz_question (auto-judged path)
      * otherwise        -> _render_quiz_landing (config + start buttons)

    Bug fix: in the previous version, pressing "next" cleared the
    current question BEFORE rerun, so the routing layer saw "no
    question" and bounced back to the landing page. The new flow
    pre-fetches the next question INTO quiz_current before rerun
    (_advance_to_next), so the next paint always has a card ready.
    """
    level = st.session_state.level.replace("-", "")
    st.markdown(f"### 🎲 背单词自测 · {level}")

    # ----- Live session summary strip -----
    sess = st.session_state.get("quiz_session")
    if sess and st.session_state.get("quiz_active"):
        attempted = int(sess.get("attempted", 0) or 0)
        correct = int(sess.get("correct", 0) or 0)
        wrong = int(sess.get("wrong", 0) or 0)
        planned = int(sess.get("planned", 0) or 0)
        rate = (correct / attempted * 100) if attempted else 0.0
        s1, s2, s3, s4 = st.columns(4)
        s1.metric("本轮进度", f"{attempted} / {planned}")
        s2.metric("答对", f"{correct}")
        s3.metric("答错", f"{wrong}")
        s4.metric("正确率", f"{rate:.1f}%")
        st.progress(min(1.0, attempted / planned) if planned else 0.0)
        st.markdown("---")

    # ----- Config row: source / direction / planned count -----
    cfg_col1, cfg_col2, cfg_col3 = st.columns([2, 2, 1])
    with cfg_col1:
        st.markdown("###### 🎯 题目来源")
        source_labels = ["📚 全部单词", "✅ 已掌握单词", "❌ 错题本"]
        source_choice = st.radio(
            "题目来源", source_labels,
            index=0, horizontal=True,
            label_visibility="collapsed", key="quiz_source",
        )
        source_key = {
            "📚 全部单词": "all",
            "✅ 已掌握单词": "mastered",
            "❌ 错题本": "wrong",
        }[source_choice]
        pool_n = _quiz_pool_size(level, source_key)
        if pool_n == 0:
            st.caption("⚠️ 该题源目前**空**")
        else:
            st.caption(f"当前题池共 **{pool_n}** 个词")

    with cfg_col2:
        st.markdown("###### 🔀 出题方向")
        dir_labels = ["英 → 中", "中 → 英", "🎲 中英随机混合"]
        dir_choice = st.radio(
            "出题方向", dir_labels,
            index=0, horizontal=True,
            label_visibility="collapsed", key="quiz_direction",
        )
        if dir_choice == "🎲 中英随机混合":
            st.caption("每道题会随机决定让你写中文还是英文")
        else:
            st.caption(f"始终让你 {dir_choice}")

    with cfg_col3:
        st.markdown("###### 📏 本轮题数")
        planned_n = st.number_input(
            "本轮题数", min_value=1, max_value=200, value=20,
            step=1, label_visibility="collapsed",
            help="本轮测试的目标题数,答完自动结算",
            key="quiz_planned_n",
        )
        st.caption(f"将随机抽 **{planned_n}** 道题")

    # If user tweaks source / direction / planned mid-session, end it.
    if st.session_state.get("quiz_active") and sess:
        if (sess.get("source_key") != source_key
                or sess.get("dir_choice") != dir_choice
                or sess.get("planned") != planned_n):
            st.session_state.quiz_active = False
            st.session_state.quiz_current = None
            st.session_state.quiz_session = None
            st.warning("题源/方向/题数已改动,本轮已自动结束")

    # ----- ROUTING -----
    if (sess and not st.session_state.get("quiz_active")
            and sess.get("ended_at") is not None):
        _render_quiz_result(level, sess)
        return

    if st.session_state.get("quiz_current"):
        _render_quiz_question(level, source_key, source_choice,
                               dir_choice, pool_n)
        return

    _render_quiz_landing(level, source_key, source_choice,
                          dir_choice, planned_n, pool_n)


def _roll_direction(dir_choice: str) -> str:
    """Per-question direction. Mixed mode rolls the dice."""
    if dir_choice == "英 → 中":
        return "英 → 中"
    if dir_choice == "中 → 英":
        return "中 → 英"
    import random as _r
    return _r.choice(["英 → 中", "中 → 英"])


def _draw_one_question(level: str, source_key: str) -> dict | None:
    """Pull one word from the pool, return a quiz-current dict."""
    word = _pick_quiz_word(level, source=source_key)
    if not word:
        return None
    return {
        "word": word,
        "judgment": "editing",
        "user_input": "",
    }


def _start_session(level: str, source_key: str, source_choice: str,
                    dir_choice: str, planned_n: int) -> bool:
    """Init session state and pre-fetch the first question."""
    import datetime as _dt
    st.session_state.quiz_session = {
        "source_key": source_key,
        "source_choice": source_choice,
        "dir_choice": dir_choice,
        "planned": int(planned_n),
        "attempted": 0,
        "correct": 0,
        "wrong": 0,
        "started_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "ended_at": None,
    }
    first = _draw_one_question(level, source_key)
    if not first:
        return False
    first["source_key"] = source_key
    first["source_choice"] = source_choice
    first["dir_choice"] = dir_choice
    first["direction"] = _roll_direction(dir_choice)
    st.session_state.quiz_current = first
    st.session_state.quiz_active = True
    return True


def _start_single_draw(level: str, source_key: str,
                        source_choice: str, dir_choice: str) -> bool:
    """Single-shot path: no session, no counters."""
    first = _draw_one_question(level, source_key)
    if not first:
        return False
    first["source_key"] = source_key
    first["source_choice"] = source_choice
    first["dir_choice"] = dir_choice
    first["direction"] = _roll_direction(dir_choice)
    st.session_state.quiz_current = first
    return True


def _render_quiz_landing(level: str, source_key: str, source_choice: str,
                          dir_choice: str, planned_n: int, pool_n: int) -> None:
    """Landing: 2 entry buttons + small recap of last session."""
    st.markdown("---")
    last = st.session_state.get("quiz_session")
    if (last and last.get("attempted", 0) > 0
            and not st.session_state.get("quiz_active")):
        rate = (last["correct"] / last["attempted"] * 100) if last["attempted"] else 0
        st.info(
            f"📊 上一轮:答对 {last['correct']} / {last['attempted']} 题,"
            f"正确率 {rate:.1f}%"
        )

    c_main, c_single = st.columns([3, 1])
    with c_main:
        if st.button(
            f"🚀 开始本轮测试 (共 {planned_n} 题)",
            type="primary", use_container_width=True,
            disabled=(pool_n == 0),
            key="quiz_start_session",
        ):
            if not _start_session(level, source_key, source_choice,
                                    dir_choice, planned_n):
                st.error("题源为空,无法开始测试。")
            st.rerun()
    with c_single:
        if st.button(
            "🎯 抽一题", use_container_width=True,
            disabled=(pool_n == 0),
            help="不开本轮,只抽一道题练手",
            key="quiz_start_single",
        ):
            if not _start_single_draw(level, source_key, source_choice,
                                        dir_choice):
                st.error("题源为空,无法抽题。")
            st.rerun()

    if pool_n == 0:
        if source_key == "mastered":
            st.warning("已掌握题源为空,请先去「📝 词汇板块」标记几个词。")
        elif source_key == "wrong":
            st.warning("错题本为空,请先去「🟥 错题本」加几个词。")


def _render_quiz_result(level: str, sess: dict) -> None:
    """End-of-session summary panel."""
    attempted = int(sess.get("attempted", 0) or 0)
    correct = int(sess.get("correct", 0) or 0)
    wrong = int(sess.get("wrong", 0) or 0)
    planned = int(sess.get("planned", 0) or 0)
    rate = (correct / attempted * 100) if attempted else 0.0
    skipped = max(0, planned - attempted)
    source = sess.get("source_choice", "")
    direction = sess.get("dir_choice", "")

    st.markdown("## 🏁 本轮测试成绩结算")
    st.caption(f"题源:{source} · 方向:{direction}")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("📋 计划题数", f"{planned}")
    m2.metric("✅ 答对", f"{correct}")
    m3.metric("❌ 答错", f"{wrong}")
    m4.metric("🎯 正确率", f"{rate:.1f}%",
              delta=f"{rate - 70:.1f} vs 70% 合格线",
              delta_color="normal" if rate >= 70 else "inverse")

    st.markdown("---")
    if attempted == 0:
        st.warning("本轮没有完成任何题目。")
    elif rate >= 90:
        st.success("🏆 卓越!你这一轮基本掌握了,继续保持。")
    elif rate >= 75:
        st.info("👍 不错!再过两轮你就能稳定在 90% 以上。")
    elif rate >= 50:
        st.warning("⚡ 还在路上 —— 错题本里已经自动收集了你的盲点,"
                    "下一轮换「❌ 错题本」题源会强很多。")
    else:
        st.error("🆘 错题很多,但错题本已经把它们存好了 —— 下一轮换"
                  "「❌ 错题本」反复练,一周内会有飞跃。")

    if skipped > 0:
        st.caption(f"⏭ 还有 {skipped} 道题没答,没被记入统计。")

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔄 开始新一轮", type="primary",
                      use_container_width=True, key="quiz_restart"):
            st.session_state.quiz_session = None
            st.session_state.quiz_active = False
            st.session_state.quiz_current = None
            st.rerun()
    with c2:
        if st.button("📚 去词汇页巩固", use_container_width=True,
                      key="quiz_goto_vocab"):
            st.info("👈 请在左侧菜单点击「📝 词汇板块」")


def _render_quiz_question(level: str, source_key: str,
                            source_choice: str, dir_choice: str,
                            pool_n: int) -> None:
    """Render the active question card + answer + judgment + nav."""
    qs = st.session_state.quiz_current
    if not qs:
        return
    sess = st.session_state.get("quiz_session")
    in_session = bool(st.session_state.get("quiz_active") and sess)

    word = qs["word"]
    direction = qs["direction"]
    if direction == "英 → 中":
        prompt = word.get("word", "")
        answer = word.get("translation", "") or "(无中文释义)"
        input_placeholder = "请输入中文释义 ..."
    else:
        prompt = word.get("translation", "") or "(无中文释义)"
        answer = word.get("word", "")
        input_placeholder = "type the English word ..."

    st.markdown(
        f"<div style='display:flex; justify-content:space-between; "
        f"align-items:center; margin-bottom:6px;'>"
        f"  <div style='font-size:12px; color:#6B7280;'>"
        f"    📂 {source_choice} · 🔀 {direction}"
        f"  </div>"
        f"  <div style='font-size:12px; color:#6B7280;'>"
        f"    ⭐ {word.get('star_rating', 0)} · "
        f"    频 {word.get('frequency', 0)}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    st.markdown("#### 题目")
    st.markdown(
        f"<div style='font-size:28px; font-weight:700; "
        f"padding:20px; background:#F1F5F9; border-radius:10px; "
        f"text-align:center; color:#0F172A;'>{prompt}</div>",
        unsafe_allow_html=True,
    )

    if "answer_revealed" in qs and "judgment" not in qs:
        qs["judgment"] = "editing"

    # ----- Branch A: editing -----
    if qs.get("judgment") == "editing":
        # Unique key per question prevents the prior question's text
        # from carrying over when the next question loads.
        user_ans = st.text_input(
            "✍️ 你的答案", value=qs.get("user_input", ""),
            key=f"quiz_input_{word['id']}",
            placeholder=input_placeholder,
        )
        qs["user_input"] = user_ans

        c_submit, c_skip = st.columns([3, 1])
        with c_submit:
            submitted = st.button(
                "📝 提交答案", type="primary",
                use_container_width=True, key="quiz_submit",
            )
        with c_skip:
            skipped = st.button(
                "😣 不会", use_container_width=True,
                key="quiz_skip",
                help="承认不会,自动加入错题本并显示答案",
            )

        if submitted:
            if not user_ans.strip():
                st.warning("请先输入答案,或点「不会」")
            else:
                ok = _judge_quiz_answer(user_ans, answer, direction)
                _apply_judgment(qs, word, ok)
                _bump_session(sess, ok)
                st.rerun()
        elif skipped:
            _apply_judgment(qs, word, False, skipped=True)
            _bump_session(sess, False)
            st.rerun()
        return

    # ----- Branch B: judged -----
    # The banners contain <svg> markup; render them via
    # components.html so React's reconciler doesn't escape the <svg>
    # tags (which would trigger a NotFoundError on re-render).
    # The relevant CSS lives in _VOCAB_CARD_CSS, which is injected
    # at the top of _render_vocabulary_tab.
    judgment = qs.get("judgment")
    if judgment == "correct":
        st.markdown(
            f'<div class="quiz-banner correct">'
            f'  <span class="vocab-banner-icon">✓</span>'
            f'  <span>恭喜你,答对了!</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    elif judgment == "wrong":
        st.markdown(
            f'<div class="quiz-banner wrong">'
            f'  <span class="vocab-banner-icon">✗</span>'
            f'  <span>答错了!正确答案:<b>{_html_escape(answer)}</b></span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:  # "skipped"
        st.markdown(
            f'<div class="quiz-banner skipped">'
            f'  <span class="vocab-banner-icon">!</span>'
            f'  <span>已记入错题本。参考答案:<b>{_html_escape(answer)}</b></span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("##### 📚 参考答案")
    st.markdown(
        f"<div style='font-size:20px; padding:12px; "
        f"background:#ECFDF5; border-left:4px solid #10B981; "
        f"border-radius:6px; color:#065F46;'>{answer}</div>",
        unsafe_allow_html=True,
    )
    alt = (word.get("translation", "") if direction == "英 → 中"
           else word.get("word", ""))
    st.caption(
        f"⭐ {word.get('star_rating', 0)} · "
        f"频率 {word.get('frequency', 0)} · "
        f"已掌握 {'✅' if word.get('mastered') else '❌'} · "
        f"互查: {alt}"
    )

    st.markdown("---")
    next_col, end_col = st.columns([3, 1])

    with next_col:
        if in_session and sess:
            is_last = int(sess.get("attempted", 0) or 0) >= int(
                sess.get("planned", 0) or 0)
            label = "🏁 答完结算" if is_last else "⏭  下一题"
            if st.button(label, type="primary",
                          use_container_width=True, key="quiz_next"):
                if is_last:
                    import datetime as _dt
                    sess["ended_at"] = _dt.datetime.now().isoformat(
                        timespec="seconds")
                    st.session_state.quiz_active = False
                    st.session_state.quiz_current = None
                else:
                    _advance_to_next(level, source_key, source_choice,
                                      dir_choice)
                st.rerun()
        else:
            if st.button("⏭  下一题", type="primary",
                          use_container_width=True, key="quiz_next_single"):
                st.session_state.quiz_current = None
                st.rerun()

    with end_col:
        if in_session:
            if st.button("🏁 结束测试", type="secondary",
                          use_container_width=True, key="quiz_end",
                          help="提前结束,立刻查看本轮成绩"):
                import datetime as _dt
                sess["ended_at"] = _dt.datetime.now().isoformat(
                    timespec="seconds")
                st.session_state.quiz_active = False
                st.session_state.quiz_current = None
                st.rerun()


def _apply_judgment(qs: dict, word: dict, ok: bool,
                     skipped: bool = False) -> None:
    """Set the judgment field on the live question + write to DB."""
    if skipped:
        qs["judgment"] = "skipped"
    else:
        qs["judgment"] = "correct" if ok else "wrong"
    try:
        if skipped or not ok:
            dm.record_wrong(int(word["id"]))
        else:
            dm.record_correct(int(word["id"]))
    except Exception as e:
        st.error(f"自动写库失败: {e}")


def _bump_session(sess: dict | None, ok: bool) -> None:
    """Increment the running counters. No-op in single-draw mode."""
    if not sess:
        return
    sess["attempted"] = int(sess.get("attempted", 0) or 0) + 1
    if ok:
        sess["correct"] = int(sess.get("correct", 0) or 0) + 1
    else:
        sess["wrong"] = int(sess.get("wrong", 0) or 0) + 1


def _advance_to_next(level: str, source_key: str, source_choice: str,
                      dir_choice: str) -> None:
    """Pre-fetch the next question into ``quiz_current`` BEFORE the
    rerun. The next paint will see the new question already in
    session_state, so the routing layer goes straight to the question
    renderer instead of the landing page.

    Pool-emptied edge case: if the source pool is exhausted (typical
    for "错题本" with only 9 words after a few draws), end the session
    gracefully instead of leaving a "no question" state.
    """
    nxt = _draw_one_question(level, source_key)
    if nxt is None:
        sess = st.session_state.get("quiz_session")
        if sess:
            import datetime as _dt
            sess["ended_at"] = _dt.datetime.now().isoformat(
                timespec="seconds")
            st.session_state.quiz_active = False
            st.session_state.quiz_current = None
        return
    nxt["source_key"] = source_key
    nxt["source_choice"] = source_choice
    nxt["dir_choice"] = dir_choice
    nxt["direction"] = _roll_direction(dir_choice)
    st.session_state.quiz_current = nxt

def _render_ai_grader() -> None:
    """Top-level AI grader page. Two modes: 写作 / 翻译, each with a
    real-exam library dropdown AND a free-form fallback.
    """
    st.markdown("## 🤖 AI 写作 / 翻译批改官")
    st.caption("历年真题直挂 · 提交即得 15 分制成绩单 + 逐句诊断 + 高分替换 + 满分范文")

    if not ai.has_api():
        st.warning("⚠️ 未配置 API Key (config.json),将使用本地启发式评分。"
                   "点击左侧「🔑 API 配置」可填入 OpenAI 兼容接口。")

    task = st.radio("批改模式", ["✍️ 写作批改", "🗣️ 翻译精批"],
                    horizontal=True, key="grader_mode")

    if task == "✍️ 写作批改":
        _render_essay_grader()
    else:
        _render_translation_grader()


def _essay_label(it: dict) -> str:
    yr = it.get("year") or 0
    sess = it.get("session") or ""
    title = (it.get("title") or it.get("topic") or "Untitled")
    return f"#{it['id']} · {yr} {sess} · {title[:30]}"


def _translation_label(it: dict) -> str:
    yr = it.get("year") or 0
    sess = it.get("session") or ""
    topic = (it.get("topic_type") or "")
    return f"#{it['id']} · {yr} {sess} · {topic[:30]}"


def _render_essay_grader() -> None:
    st.markdown("#### ✍️ 写作 AI 精批")
    level = st.session_state.level.replace("-", "")

    # ----- 真题下拉 -----
    writing_items = dm.list_writing(level)
    options = ["📝 自由出题 (不指定题面)"] + [_essay_label(w) for w in writing_items]
    pick = st.selectbox(
        "📚 历年真题 (选一道 → 自动带出题面)",
        options, index=0, key="grader_essay_pick",
    )
    chosen = None
    if pick and not pick.startswith("📝"):
        # find by id from the label
        try:
            chosen_id = int(pick.split("·")[0].strip().lstrip("#"))
            chosen = next((w for w in writing_items if w["id"] == chosen_id), None)
        except Exception:
            chosen = None

    # ----- 题面 / 题目要求展示 -----
    if chosen:
        st.info(
            f"### 📌 {chosen.get('title') or chosen.get('topic','(题目)')}\n\n"
            f"{chosen.get('requirements') or chosen.get('topic') or '(题目要求见上方)'}"
        )
        # 关键短语徽章
        kp = (chosen.get("key_phrases") or "").strip()
        if kp:
            phrases = [p.strip() for p in kp.replace("，", ",").split(",") if p.strip()]
            if phrases:
                chips = " ".join(
                    f"<span style='display:inline-block; background:#FEF3C7; "
                    f"color:#92400E; padding:2px 8px; border-radius:999px; "
                    f"font-size:12px; margin:2px 4px 2px 0;'>{p}</span>"
                    for p in phrases[:12]
                )
                st.markdown(
                    f"<div style='margin:6px 0 12px 0;'>"
                    f"<span style='color:#6B7280; font-size:13px;'>📚 关键短语: </span>"
                    f"{chips}</div>",
                    unsafe_allow_html=True,
                )
        topic = chosen.get("title") or chosen.get("topic") or ""
        db_sample_essay = (chosen.get("sample_essay") or "").strip()
    else:
        topic = st.text_input("📌 题目 (自由出题时填,无则不传)",
                              value="", key="grader_free_topic")
        db_sample_essay = ""

    # ----- 录入区 -----
    essay = st.text_area(
        "✍️ 你的作文 (建议 80 词以上,真实考试 120-180 词)",
        height=260, key="grader_essay",
        placeholder="Paste / type your essay here ...",
    )

    # ----- 提交 -----
    if st.button("🤖 提交 AI 批改", type="primary",
                  use_container_width=True, key="grader_essay_submit"):
        if len(essay.strip()) < 30:
            st.error("作文太短,至少 30 字符。")
            return
        with st.spinner("AI 阅卷官正在精批 (10-30 秒)..."):
            try:
                result = ai.grade_essay(topic or "（无题面）", essay)
            except Exception as e:
                st.error(f"AI 批改失败: {e}")
                return
        if not result:
            st.warning("AI 返回空,使用本地启发式兜底。")
            result = {"score": 0, "errors": [], "upgrades": [],
                       "polished": essay, "summary": "本地兜底评分"}
        _render_essay_report(result, sample_essay=db_sample_essay,
                              topic=topic, user_essay=essay)


def _render_essay_report(r: dict, sample_essay: str = "",
                          topic: str = "", user_essay: str = "") -> None:
    """4-section luxury report."""
    score = int(r.get("score") or 0)
    if score >= 13:
        color, label = "#10B981", "🏆 卓越"
    elif score >= 10:
        color, label = "#3B82F6", "👍 良好"
    elif score >= 7:
        color, label = "#F59E0B", "⚠️ 待加强"
    else:
        color, label = "#EF4444", "🆘 危险"

    # ----- 1. 成绩看板 -----
    st.markdown(
        f"""
        <div style="padding:22px 24px; border-radius:14px;
                    background:linear-gradient(135deg, {color}22 0%, {color}05 100%);
                    border-left:6px solid {color}; margin-bottom:16px;
                    box-shadow:0 4px 12px {color}11;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <div style="font-size:13px; color:#6B7280; letter-spacing:1px;">
                        📊 官方 15 分制评分
                    </div>
                    <div style="font-size:56px; font-weight:800; color:{color};
                                line-height:1.05; margin-top:4px;">
                        {score}<span style="font-size:24px; color:#9CA3AF;
                                          font-weight:600;"> / 15</span>
                    </div>
                </div>
                <div style="text-align:right;">
                    <div style="font-size:22px; font-weight:700; color:{color};">
                        {label}
                    </div>
                    <div style="font-size:12px; color:#6B7280; margin-top:4px;">
                        70 分 = 10.5/15 及格
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if r.get("summary"):
        st.markdown("##### 📝 总评")
        st.info(r["summary"])

    # ----- 2. 语法与词汇纠错表 -----
    errs = r.get("errors") or []
    if errs:
        st.markdown("##### 🟥 逐句纠错表")
        for e in errs:
            if not isinstance(e, dict):
                st.markdown(f"- {e}")
                continue
            st.markdown(
                f"""
                <div style="border-left:4px solid #EF4444;
                            background:linear-gradient(135deg,#FEE2E2 0%,#FEF2F2 100%);
                            padding:12px 14px; border-radius:8px; margin:8px 0;">
                    <div style="font-size:13px; color:#6B7280;">❌ 原句</div>
                    <div style="font-size:15px; color:#991B1B; font-weight:600;
                                margin:4px 0 8px 0;">{_html_escape(e.get('snippet',''))}</div>
                    <div style="font-size:13px; color:#6B7280;">🔍 问题</div>
                    <div style="font-size:14px; color:#7F1D1D; margin:2px 0 6px 0;">
                        {_html_escape(e.get('issue',''))}</div>
                    <div style="font-size:13px; color:#6B7280;">✅ 修改后</div>
                    <div style="font-size:15px; color:#065F46; font-weight:600;
                                margin:2px 0 0 0;">{_html_escape(e.get('fix',''))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.caption("✅ AI 未发现明显语病 (good!)")

    # ----- 3. 高分词汇升级 -----
    ups = r.get("upgrades") or []
    if ups:
        st.markdown("##### 💎 高分词汇升级 (低级→高级)")
        # Render as 2-col table-like rows
        for u in ups:
            if not isinstance(u, dict):
                st.markdown(f"- {u}")
                continue
            st.markdown(
                f"""
                <div style="display:flex; align-items:center; gap:8px;
                            background:#F0F9FF; border:1px solid #BAE6FD;
                            padding:10px 14px; border-radius:8px; margin:6px 0;">
                    <span style="background:#FEE2E2; color:#991B1B; padding:3px 10px;
                                 border-radius:6px; font-weight:600; text-decoration:line-through;">
                        {_html_escape(u.get('from',''))}
                    </span>
                    <span style="font-size:20px; color:#3B82F6;">→</span>
                    <span style="background:#DCFCE7; color:#166534; padding:3px 10px;
                                 border-radius:6px; font-weight:700;">
                        {_html_escape(u.get('to',''))}
                    </span>
                    <span style="flex:1; font-size:12px; color:#475569; margin-left:8px;">
                        {_html_escape(u.get('reason',''))}
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.caption("(本次未返回替换建议)")

    # ----- 4. AI 压箱底范文 -----
    st.markdown("##### 🌟 满分范文")
    # 优先用 LLM 的 polished, 没拿到就 fallback 到 DB 自带 sample_essay
    polished = (r.get("polished") or "").strip()
    if polished and polished != user_essay and len(polished) > 80:
        _show_essay_block("🤖 AI 润色版", polished, "#10B981")
    elif sample_essay and len(sample_essay) > 80:
        st.caption("(AI 未生成范文,展示数据库自带真题范文)")
        _show_essay_block("📚 真题参考范文", sample_essay, "#3B82F6")
    else:
        st.caption("本次未生成范文,可手动重试或换题再批。")


def _show_essay_block(heading: str, text: str, accent_color: str) -> None:
    """Render a single essay block (AI polished OR DB sample)."""
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg, {accent_color}11 0%, #FFFFFF 100%);
                    border-left:5px solid {accent_color}; border-radius:10px;
                    padding:18px 20px; margin:8px 0 16px 0;
                    font-family:Georgia, 'Times New Roman', serif;
                    line-height:1.85; font-size:15px; color:#1F2937;">
            <div style="font-size:13px; color:{accent_color}; font-weight:600;
                        margin-bottom:8px; letter-spacing:1px;">{heading}</div>
            {_html_escape(text).replace(chr(10), "<br>")}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_translation_grader() -> None:
    st.markdown("#### 🗣️ 翻译 AI 逐句精批")
    level = st.session_state.level.replace("-", "")

    trans_items = dm.list_translation(level)
    options = ["📝 自由输入中文原文"] + [_translation_label(t) for t in trans_items]
    pick = st.selectbox(
        "📚 历年真题 (选一道 → 自动带出中文原文 + 参考译文)",
        options, index=0, key="grader_trans_pick",
    )
    chosen = None
    if pick and not pick.startswith("📝"):
        try:
            cid = int(pick.split("·")[0].strip().lstrip("#"))
            chosen = next((t for t in trans_items if t["id"] == cid), None)
        except Exception:
            chosen = None

    # ----- 题面 / 中文原文展示 -----
    if chosen:
        zh = chosen.get("chinese_text") or ""
        ref = chosen.get("english_reference") or chosen.get("english_translation") or ""
        st.info(
            f"### 📌 {chosen.get('topic_type','翻译题')}\n\n"
            f"**中文原文:**\n\n{zh}"
        )
        with st.expander("📤 查看官方参考译文 (作答前别看)", expanded=False):
            st.write(ref or "(此题暂无官方参考译文)")

    # ----- 录入区 -----
    if chosen:
        st.markdown("##### ✍️ 你的翻译")
        student = st.text_area(
            "把你的英文翻译粘在这里", height=200,
            key="grader_trans_student",
            placeholder="Your English translation ...",
        )
        zh_for_call = chosen.get("chinese_text") or ""
        ref_for_call = chosen.get("english_reference") or chosen.get("english_translation") or ""
    else:
        st.markdown("##### ✍️ 自由翻译")
        zh = st.text_area("📥 中文原文", height=100,
                           key="grader_trans_zh",
                           placeholder="要翻译的中文段落 ...")
        ref = st.text_area("📤 参考译文 (可选,留空 AI 自动生成)",
                            height=100, key="grader_trans_ref",
                            placeholder="(留空则 AI 自动生成参考译文)")
        student = st.text_area("✍️ 你的翻译", height=160,
                                key="grader_trans_student_free",
                                placeholder="Your English translation ...")
        zh_for_call = zh
        ref_for_call = ref

    if st.button("🤖 提交 AI 精批", type="primary",
                  use_container_width=True, key="grader_trans_submit"):
        if not zh_for_call.strip() or not student.strip():
            st.error("中文原文和你的翻译都不能为空。")
            return
        with st.spinner("AI 老师正在逐句精批 (10-30 秒)..."):
            try:
                result = ai.grade_translation_line_by_line(
                    zh_for_call, ref_for_call or "", student
                )
            except Exception as e:
                st.error(f"AI 批改失败: {e}")
                return
        if not result:
            st.warning("AI 返回空,使用本地启发式兜底。")
            result = {"summary": "(本地兜底)", "missing_points": [],
                       "chinglish": [], "upgrades": [], "polished": student}
        _render_translation_report(result, ref=ref_for_call)


def _render_translation_report(r: dict, ref: str = "") -> None:
    """4-section luxury translation report."""
    if r.get("summary"):
        st.markdown("##### 📝 总评")
        st.info(r["summary"])

    # ----- 1. 采分点遗漏 -----
    miss = r.get("missing_points") or []
    if miss:
        st.markdown("##### 🔴 采分点遗漏 (你漏译的关键词)")
        for m in miss:
            st.markdown(
                f"<div style='background:#FEE2E2; color:#991B1B; "
                f"padding:8px 14px; border-radius:6px; margin:4px 0; "
                f"border-left:3px solid #EF4444;'>"
                f"⚠️ {_html_escape(str(m))}</div>",
                unsafe_allow_html=True,
            )

    # ----- 2. 中式英语硬伤 -----
    ch = r.get("chinglish") or []
    if ch:
        st.markdown("##### ⚠️ 中式英语硬伤")
        for e in ch:
            if not isinstance(e, dict):
                st.markdown(
                    f"<div style='background:#FEF3C7; color:#92400E; "
                    f"padding:8px 14px; border-radius:6px; margin:4px 0;'>"
                    f"⚠️ {_html_escape(str(e))}</div>",
                    unsafe_allow_html=True,
                )
                continue
            st.markdown(
                f"""
                <div style="border-left:4px solid #F59E0B;
                            background:linear-gradient(135deg,#FEF3C7 0%,#FFFBEB 100%);
                            padding:12px 14px; border-radius:8px; margin:8px 0;">
                    <div style="font-size:13px; color:#92400E;">📌 学生原句</div>
                    <div style="font-size:14px; color:#1F2937; font-style:italic;
                                margin:4px 0 8px 0;">
                        _{_html_escape(e.get('sentence',''))}_
                    </div>
                    <div style="font-size:13px; color:#92400E;">🔍 问题</div>
                    <div style="font-size:14px; color:#7F1D1D; margin:2px 0 6px 0;">
                        {_html_escape(e.get('issue',''))}</div>
                    <div style="font-size:13px; color:#92400E;">✅ 建议改写</div>
                    <div style="font-size:14px; color:#065F46; font-weight:600;
                                margin:2px 0 0 0;">{_html_escape(e.get('fix',''))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # ----- 3. 高级替换 -----
    ups = r.get("upgrades") or []
    if ups:
        st.markdown("##### 💎 高级替换建议 (低级 → 高级学术表达)")
        for u in ups:
            if not isinstance(u, dict):
                continue
            st.markdown(
                f"""
                <div style="display:flex; align-items:center; gap:8px;
                            background:#F0F9FF; border:1px solid #BAE6FD;
                            padding:10px 14px; border-radius:8px; margin:6px 0;">
                    <span style="background:#FEE2E2; color:#991B1B; padding:3px 10px;
                                 border-radius:6px; font-weight:600;
                                 text-decoration:line-through;">
                        {_html_escape(u.get('from',''))}
                    </span>
                    <span style="font-size:20px; color:#3B82F6;">→</span>
                    <span style="background:#DCFCE7; color:#166534; padding:3px 10px;
                                 border-radius:6px; font-weight:700;">
                        {_html_escape(u.get('to',''))}
                    </span>
                    <span style="flex:1; font-size:12px; color:#475569; margin-left:8px;">
                        {_html_escape(u.get('reason',''))}
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # ----- 4. 润色版 / 满分译文 -----
    polished = (r.get("polished") or "").strip()
    if polished and len(polished) > 20:
        st.markdown("##### 🌟 AI 润色版 (满分译文)")
        st.markdown(
            f"""
            <div style="background:linear-gradient(135deg,#10B98111 0%, #FFFFFF 100%);
                        border-left:5px solid #10B981; border-radius:10px;
                        padding:18px 20px; margin:8px 0 16px 0;
                        font-family:Georgia, 'Times New Roman', serif;
                        line-height:1.85; font-size:15px; color:#1F2937;">
                {_html_escape(polished).replace(chr(10), '<br>')}
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif ref:
        st.markdown("##### 🌟 官方参考译文 (fallback)")
        st.markdown(
            f"<div style='background:#F8FAFC; border-left:4px solid #94A3B8; "
            f"padding:14px 18px; border-radius:8px; line-height:1.7;'>"
            f"{_html_escape(ref).replace(chr(10), '<br>')}</div>",
            unsafe_allow_html=True,
        )


# ===========================================================================
# Sidebar
# ===========================================================================
def _render_sidebar() -> str:
    """Editorial masthead + chapter index in the sidebar.

    The masthead (CET 智胜 / Issue / colophon-style date) is rendered
    via plain ``st.markdown(unsafe_allow_html=True)`` with NO <svg>
    inside it. Radio buttons are the same as before but pre-styled
    to look like a chapter index via the master CSS injected once at
    app start.
    """
    with st.sidebar:
        st.markdown(web_ui.render_sidebar_masthead(), unsafe_allow_html=True)

        # ----- Exam level selector -----
        st.markdown(
            '<div class="nav-chapter">Examination Level</div>',
            unsafe_allow_html=True,
        )
        new_level = st.radio(
            "Level",
            ["CET-4", "CET-6"],
            index=0 if st.session_state.level == "CET-4" else 1,
            label_visibility="collapsed",
            key="sidebar_level",
        )
        if new_level != st.session_state.level:
            st.session_state.level = new_level
            st.rerun()

        # ----- Chapter index -----
        st.markdown(
            '<div class="nav-chapter">Chapter Index · 章节</div>',
            unsafe_allow_html=True,
        )
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
            key="sidebar_page",
        )

        # ----- API config (kept simple, no SVG) -----
        st.markdown(
            '<div class="nav-chapter">Configuration</div>',
            unsafe_allow_html=True,
        )
        with st.expander("🔑 API 配置"):
            # The values are read from st.secrets (or fallback sources)
            # by AIService on boot. We display them here for visibility
            # only — saving is a no-op in cloud deploys because the
            # authoritative copy lives in the Streamlit Cloud Secrets
            # UI. For local dev, AIService.save_config() writes
            # config.json, but only when that file is writable.
            if ai.has_api():
                st.caption("✓ 当前 API 已配置")
                st.caption(
                    f"Base URL: `{ai.config.get('base_url','')}`  ·  "
                    f"Model: `{ai.config.get('model','')}`"
                )
                key_len = len(ai.config.get("api_key", "") or "")
                if key_len:
                    st.caption(f"API Key: `sk-…` (长 {key_len}, 已被保护)")
            else:
                st.warning(
                    "⚠️ 未配置 API。运行本地时把 `api_key` 填进项目根目录 "
                    "`config.json`;部署到 Streamlit Cloud 后,在 Cloud 后台 "
                    "Settings → Secrets 里填写 `OPENAI_API_KEY` / "
                    "`OPENAI_BASE_URL` / `OPENAI_MODEL`。"
                )
            # Local-dev only: still allow editing if config.json exists.
            # In cloud deploys the file is read-only and the save
            # button is hidden.
            if Path("config.json").exists() and Path("config.json").is_file():
                st.divider()
                st.caption("🔧 本地 config.json 维护(只读,改动不会上传云端)")
                with st.form(key="local_cfg_form"):
                    base = st.text_input(
                        "Base URL", value=ai.config.get("base_url", ""))
                    key = st.text_input(
                        "API Key", value=ai.config.get("api_key", ""),
                        type="password")
                    model = st.text_input(
                        "Model", value=ai.config.get("model",
                                                      "gpt-3.5-turbo"))
                    saved = st.form_submit_button(
                        "💾 写入 config.json", use_container_width=True)
                    if saved:
                        ai.config["base_url"] = base.strip()
                        ai.config["api_key"] = key.strip()
                        ai.config["model"] = model.strip()
                        try:
                            ai.save_config()
                            st.success("✓ 已写入本地 config.json")
                        except Exception as e:
                            st.error(f"保存失败:{e}")
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


def _render_practice_session(kind: str,
                              items: list[dict] | None = None,
                              source_label: str = "") -> None:
    """Unified reading + listening practice flow.

    ``kind`` is ``'reading'`` or ``'listening'``. Reading shows the passage
    inline; listening shows an audio player and folds the transcript into
    an expander so the user can self-test before peeking.

    ``items`` (optional) — when provided, use this list instead of pulling
    from the default table. Used by the reading tab to feed filtered
    real-exam rows OR AI-generated rows from generated_practice.
    ``source_label`` is shown next to the title (e.g. "🤖 AI 预测题")
    so the user can tell which slice they're on.
    """
    level = st.session_state.level.replace("-", "")
    title = "📰 阅读训练" if kind == "reading" else "🎧 听力训练"
    suffix = f" · {source_label}" if source_label else ""
    st.markdown(f"## {title} · {level}{suffix}")

    if items is None:
        items = (dm.list_reading(level) if kind == "reading"
                 else dm.list_listening(level))
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

    # Stash the selected item so other renderers (e.g. the long-sentence
    # expander on the reading tab) can read its analysis / passage.
    st.session_state[f"current_picked_{kind}"] = item

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
    """Reading practice page — three slices stacked vertically:

    1. **Filter bar** — pick year, topic, source (real exam vs AI generated)
    2. **Real-exam slice** — pulled from the ``reading`` table, fed into
       the unified ``_render_practice_session("reading")`` so it has
       the same submit / score / AI-explain flow as before.
    3. **AI-generated slice** — one click on 🪄 calls
       ``ai.generate_similar_reading_llm()`` against the currently
       selected real exam, persists the result in
       ``generated_practice``, and re-renders so the new item shows
       up at the top of the AI slice. Items in the AI slice are
       clickable so the user can also practice them.

    The "topic" filter proxies for the official "仔细阅读 / 选词填空
    / 长篇匹配" types — the DB doesn't have those labels, but
    ``topic_type`` carries the same kind of topical clustering
    (e.g. "心理学", "教育") that the real exam papers use to slice
    their 4-5 篇文章.
    """
    level = st.session_state.level.replace("-", "")
    st.markdown(f"## 📰 阅读训练 · {level}")

    # ============================================================
    # Filter bar
    # ============================================================
    all_real = dm.list_reading(level)

    # Year dropdown — "全部" first
    years = sorted({r.get("year") for r in all_real
                    if r.get("year") not in (None, 0)}, reverse=True)
    year_labels = ["全部年份"] + [f"{y} 年" for y in years]

    # Topic dropdown — only the "useful" topics (drop 综合 / 练习 / none)
    _USEFUL_TOPICS = {
        "心理学", "教育", "职场", "经济/金融", "经济/政策", "社会/科技",
        "环境", "科普", "心理/生活", "教育/科技", "语言/认知", "健康",
    }
    topic_counter: dict[str, int] = {}
    for r in all_real:
        t = (r.get("topic_type") or "").strip()
        if t and t in _USEFUL_TOPICS:
            topic_counter[t] = topic_counter.get(t, 0) + 1
    topic_labels = ["全部题材"] + sorted(topic_counter.keys())

    f1, f2, f3 = st.columns([1, 2, 2])
    with f1:
        year_choice = st.selectbox(
            "📅 年份", year_labels, index=0,
            key="reading_year", label_visibility="collapsed",
        )
    with f2:
        topic_choice = st.selectbox(
            "📚 题材", topic_labels, index=0,
            key="reading_topic", label_visibility="collapsed",
        )
    with f3:
        source_choice = st.radio(
            "📂 题源", ["📚 真题", "🤖 AI 预测题", "📚+🤖 全部"],
            index=0, horizontal=True, label_visibility="collapsed",
            key="reading_source",
        )

    # Apply filters to real-exam slice
    real_filtered = all_real
    if year_choice != "全部年份":
        y = int(year_choice.split()[0])
        real_filtered = [r for r in real_filtered if r.get("year") == y]
    if topic_choice != "全部题材":
        real_filtered = [r for r in real_filtered
                          if (r.get("topic_type") or "").strip() == topic_choice]

    # ============================================================
    # Real-exam slice
    # ============================================================
    st.caption(
        f"📚 真题命中: {len(real_filtered)} 篇 "
        f"(原始库 {len(all_real)} 篇,题材/年份已过滤)"
    )

    if source_choice in ("📚 真题", "📚+🤖 全部") and real_filtered:
        _render_practice_session("reading", real_filtered)
    elif source_choice == "📚 真题":
        st.info("按当前年份/题材过滤后没有真题,试试切到「全部」")

    # ============================================================
    # AI-generated slice
    # ============================================================
    if source_choice in ("🤖 AI 预测题", "📚+🤖 全部"):
        st.markdown("---")
        st.markdown("### 🤖 AI 同源预测题 (generated_practice)")
        ai_items = _collect_ai_reading_items(level)
        st.caption(
            f"🤖 AI 题命中: {len(ai_items)} 篇 "
            f"· 调用 ai.generate_similar_reading_llm() 实时生成"
        )
        # 🪄 Generate button — only enabled when a real exam is in view
        gen_disabled = len(real_filtered) == 0
        gen_help = ("请先在上面选好一个真题年份/题材,"
                    "AI 会仿照当前真卷的风格生成同源预测题"
                    if not gen_disabled else
                    "需要先在真题库中至少选出一篇才能生成同源预测题")
        if st.button(
            "🪄 AI 现编一炉:基于当前筛选生成同源预测练兵题",
            type="primary", use_container_width=True,
            disabled=gen_disabled, help=gen_help,
            key="reading_ai_generate",
        ):
            with st.spinner("AI 命题老师正在挥笔原创中... (10-30 秒)"):
                _generate_and_save_ai_reading(level, real_filtered)
            st.success("✓ 已生成并入库,滚动到下方「AI 同源预测题」选做。")
            st.rerun()

        if ai_items:
            _render_practice_session("reading", ai_items, source_label="🤖 AI 预测题")
        else:
            st.caption("点上方按钮生成第一篇 AI 同源题,生成后会出现在这里。")

    # ============================================================
    # Long-sentence / headline-analysis expander
    # ============================================================
    # Sits below the AI slice so it always shows analysis for whatever
    # the user last picked in the real-exam picker (the AI picker is
    # its own slot).
    picked = st.session_state.get("current_picked_reading")
    if source_choice in ("📚 真题", "📚+🤖 全部") and picked and not picked.get("_is_ai"):
        analysis = (picked.get("analysis") or "").strip()
        if analysis:
            with st.expander("🤖 AI 考点长难句深度拆解 (基于当前真题)",
                              expanded=False):
                st.markdown(analysis)
        else:
            with st.expander("🤖 AI 考点长难句深度拆解", expanded=False):
                st.caption("此篇暂无官方/原始解析,可在答题卡点「🧐 AI 讲解」逐题生成。")


# ---------------------------------------------------------------------------
# AI reading helpers
# ---------------------------------------------------------------------------
def _collect_ai_reading_items(level: str) -> list[dict]:
    """Read generated_practice rows and shape them to look like
    ``reading`` rows so they can be fed straight into
    ``_render_practice_session(kind='reading')``."""
    import json as _json
    rows = dm.list_generated("reading", level)
    out = []
    for r in rows:
        content = r.get("content") or ""
        # Content was saved as JSON-encoded payload: {title, passage,
        # questions:[{q, options, answer, analysis}]}. We defensively
        # parse: handle nested string-questions (old buggy rows) and
        # malformed entries by surfacing a minimal card with a warning
        # rather than silently dropping the item.
        title, passage, questions, answers = "", "", [], ""
        try:
            data = _json.loads(content)
            if isinstance(data, dict):
                title = data.get("title") or r.get("title") or ""
                passage = data.get("passage") or ""
                qs = data.get("questions") or []
                # questions may itself be a string (old buggy rows)
                if isinstance(qs, str):
                    try:
                        qs = _json.loads(qs)
                    except Exception:
                        qs = []
                if not isinstance(qs, list):
                    qs = []
                # Normalise each q to {"q", "options": [...4 strings...]}
                cleaned = []
                for q in qs:
                    if not isinstance(q, dict):
                        continue
                    opts = q.get("options") or []
                    if isinstance(opts, str):
                        try:
                            opts = _json.loads(opts)
                        except Exception:
                            opts = []
                    if not isinstance(opts, list):
                        opts = []
                    # Ensure 4 entries; pad with placeholder if short
                    opts = [str(o) for o in opts[:4]]
                    while len(opts) < 4:
                        opts.append(f"({len(opts)+1}) (选项缺失)")
                    # Prepend letter prefix if missing
                    prefixed = []
                    for i, opt in enumerate(opts):
                        letter = "ABCD"[i]
                        if not opt[:3].startswith(f"{letter}."):
                            prefixed.append(f"{letter}. {opt}")
                        else:
                            prefixed.append(opt)
                    cleaned.append({"q": str(q.get("q", "")).strip(),
                                     "options": prefixed,
                                     "answer": str(q.get("answer", "?")).strip().upper()[:1]})
                questions = cleaned
                answers = " ".join(q["answer"] for q in cleaned)
            else:
                passage = str(data)
        except Exception:
            passage = content

        out.append({
            "id": f"ai_{r.get('id')}",
            "level": level,
            "year": None,
            "session": "AI",
            "passage_title": title or r.get("title") or "AI 预测篇",
            "passage": passage,
            "questions": _json.dumps(questions, ensure_ascii=False),
            "answers": answers,
            "analysis": r.get("analysis") or "",
            "topic_type": "AI预测",
            "_is_ai": True,
            "_gen_id": r.get("id"),
        })
    return out


def _generate_and_save_ai_reading(level: str,
                                    real_filtered: list[dict]) -> None:
    """Pick a random real exam from the current filter, ask the LLM for
    a fresh same-style passage + 3-5 questions, persist to
    generated_practice.

    Falls back to the template engine ``generate_similar_reading`` if
    no API key is configured OR the LLM call fails. Either way the
    result is saved so the user always sees a new item.
    """
    import json as _json
    import random as _r
    if not real_filtered:
        st.warning("当前筛选下没有真题,无法生成同源题。请放宽条件。")
        return

    seed = _r.choice(real_filtered)
    try:
        llm_result = ai.generate_similar_reading_llm(seed) if ai.has_api() else None
    except Exception as e:
        st.warning(f"LLM 调用失败,改用本地模板兜底: {e}")
        llm_result = None
    try:
        tpl_result = ai.generate_similar_reading(seed) if not llm_result else None
    except Exception:
        tpl_result = None
    result = llm_result or tpl_result
    if not result:
        st.error("AI 生成完全失败,本地模板也没数据。请检查 API 配置。")
        return

    # ----- Defensive parsing: questions can be list OR JSON-encoded str
    # depending on which generator produced the result. Some LLM paths
    # serialise the list back into a string. Always normalise to list.
    raw_qs = result.get("questions") or []
    if isinstance(raw_qs, str):
        try:
            raw_qs = _json.loads(raw_qs)
        except Exception:
            raw_qs = []
    if not isinstance(raw_qs, list):
        raw_qs = []

    # Normalise each question dict: {"q", "options":[4], "answer":"A"}
    # If a question is missing the 4 options, treat the whole batch as
    # malformed and surface a clear error.
    norm_qs = []
    for q in raw_qs:
        if not isinstance(q, dict):
            continue
        opts = q.get("options") or []
        if isinstance(opts, str):
            try:
                opts = _json.loads(opts)
            except Exception:
                opts = []
        if not isinstance(opts, list) or len(opts) < 2:
            continue
        # Prepend "A. " / "B. " / etc. if missing so the radio buttons
        # in the UI render with their letters, mirroring the LLM path.
        prefixed = []
        for i, opt in enumerate(opts[:4]):
            letter = "ABCD"[i]
            opt_s = str(opt).strip()
            if not opt_s[:3].startswith(f"{letter}."):
                prefixed.append(f"{letter}. {opt_s}")
            else:
                prefixed.append(opt_s)
        norm_qs.append({
            "q": str(q.get("q", "")).strip(),
            "options": prefixed,
            "answer": str(q.get("answer", "?")).strip().upper()[:1],
            "analysis": str(q.get("analysis", "")).strip(),
        })

    if not norm_qs:
        st.error(
            "AI 生成的题目缺少 4 选项,已丢弃。"
            "LLM/模板输出可能不规范,试试再点一次或换题材。"
        )
        return

    payload = {
        "title": result.get("title") or f"AI 同源: {seed.get('passage_title','?')[:20]}",
        "passage": result.get("passage", ""),
        "questions": norm_qs,
    }
    answers_text = result.get("answers") or " ".join(
        q["answer"] for q in norm_qs
    )
    try:
        new_id = dm.save_generated_practice(
            section="reading",
            level=level,
            parent_id=int(seed.get("id", 0)) if str(seed.get("id", "")).isdigit() else 0,
            title=payload["title"][:120],
            content=_json.dumps(payload, ensure_ascii=False),
            answers=answers_text,
            analysis=result.get("analysis") or "",
        )
        st.session_state[f"reading_last_gen_id"] = new_id
    except Exception as e:
        st.error(f"AI 题入库失败: {e}")


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
    # Inject the editorial design system exactly once at app start.
    # Pure HTML <style> body — no <svg> tags, no @keyframes that
    # mutate React-owned nodes. The browser dedupes identical
    # <style> blocks across reruns, so the call is idempotent.
    web_ui.inject_design_css()

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

    # Editorial colophon footer — replaces the plain "© CET 智胜 V2.1" caption
    st.markdown(
        '<div style="margin-top:40px; padding-top:14px; border-top:1px solid #D8CFB8;'
        '            text-align:center; font-family:\'Playfair Display\', Georgia, serif;'
        '            font-size:12px; color:#9A8F7B; letter-spacing:0.18em;'
        '            text-transform:uppercase; font-style:italic;">'
        'CET 智胜 · set in Playfair &amp; Source Serif · printed on cream paper'
        '</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
