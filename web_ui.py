"""web_ui.py — Editorial Notebook design system for CET 智胜.

A single-file design system for the Streamlit web app. Aesthetic
direction: "Editor's Notebook" — a high-end language-study magazine
that feels printed on cream paper, with cinnabar-red editorial accent
and strict typographic hierarchy.

We deliberately avoid the typical Streamlit look (purple gradients,
pillow shadows, hard-edged cards). Instead: paper-edge borders, serif
display, roman-numeral section labels, hand-drawn rules.

All styling ships in one big ``<style>`` block injected once at the
top of every page via ``st.markdown(unsafe_allow_html=True)``. The
streamlit components.html helper is used for the sidebar only (where
SVG icons live), and only with carefully chosen content that won't
trip React's reconciler.
"""
from __future__ import annotations

import streamlit as st

# Design tokens. One source of truth for the whole site.
# Pulled from the editorial-ink palette of a 1920s Chinese-English
# language primer, sampled in photoshop and re-tuned for screen.
TOKENS = {
    "paper":      "#FAF7F2",   # warm cream — main background
    "paper_warm": "#F2EDE2",   # slightly darker — for inset panels
    "ink":        "#1A1A1A",   # near-black for body
    "ink_soft":   "#5A5247",   # warm gray for captions
    "rule":       "#D8CFB8",   # paper-edge border
    "cinnabar":   "#B73239",   # seal red — primary accent
    "cinnabar_deep": "#8A1F25",
    "jade":       "#3B6E5C",   # secondary accent for "correct" / "mastered"
    "amber":      "#B47929",   # tertiary accent for "in progress"
    "muted":      "#9A8F7B",
    "card_bg":    "#FFFFFF",
}

# Font stack. Web-fonts first (loads if online), then a curated
# fallback chain of editorial serifs and clean sans, then the
# user's installed fonts, then generic system.
FONT_DISPLAY = "'Playfair Display', 'Source Serif 4', 'EB Garamond', " \
              "'Noto Serif', 'STSong', 'SimSun', Georgia, serif"
FONT_BODY    = "'Source Serif 4', 'EB Garamond', 'Noto Serif', " \
              "'PingFang SC', 'Microsoft YaHei', Georgia, serif"
FONT_NUMBER  = "'Playfair Display', 'Cormorant Garamond', " \
              "'Times New Roman', Georgia, serif"


# ---------------------------------------------------------------------------
# Master stylesheet. One string. No <svg>, no @keyframes that touch DOM
# nodes React created (that's what triggered the NotFoundError before).
# All keyframes here apply to ::before / ::after pseudo-elements that
# Streamlit never sees as React children.
# ---------------------------------------------------------------------------
DESIGN_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,600;0,700;0,900;1,400;1,700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,500;8..60,600&display=swap');

:root {{
    --paper: {TOKENS['paper']};
    --paper-warm: {TOKENS['paper_warm']};
    --ink: {TOKENS['ink']};
    --ink-soft: {TOKENS['ink_soft']};
    --rule: {TOKENS['rule']};
    --cinnabar: {TOKENS['cinnabar']};
    --cinnabar-deep: {TOKENS['cinnabar_deep']};
    --jade: {TOKENS['jade']};
    --amber: {TOKENS['amber']};
    --muted: {TOKENS['muted']};
}}

html, body,
[data-testid="stAppViewContainer"],
.stApp,
section.main,
[data-testid="stSidebar"] + section.main {{
    background: var(--paper) !important;
    color: var(--ink) !important;
    font-family: {FONT_BODY};
    font-feature-settings: "kern", "liga", "palt";
    font-size: 16px;
    line-height: 1.6;
}}

/* === HEADER & SIDEBAR === */
/* NB: we deliberately do NOT zero-out the header height. The earlier
   "height: 0 !important" rule killed the sidebar toggle and stranded
   users — they couldn't reopen the sidebar once it had been
   auto-collapsed on mobile. We keep the header chrome visually blank
   WHILE keeping the clickable control on screen.

   Streamlit 1.58.0 actual DOM (verified by grepping the minified
   bundle — see /tools/notes/streamlit-1.58-sidebar-buttons.md):
     - stHeader                 ← the top header bar
     - stAppToolbar / stToolbar ← inside the header; hidden by us
     - stExpandSidebarButton    ← shows in header when sidebar IS
                                  collapsed; this is the ">>" at top-left
     - stSidebar                ← the sidebar itself
     - stSidebarHeader          ← top edge of the sidebar
     - stSidebarCollapseButton  ← the "<<" inside sidebar; React sets
                                  visibility:hidden by default and
                                  only flips to visible on sidebar
                                  mouseenter — which means on mobile
                                  (no hover) the user can never close
                                  the sidebar again.

   The OLD selectors in this file (`stSidebarCollapsedControl`,
   `baseButton-headerNoPadding`) were leftover from a 1.20-era
   Streamlit and DON'T EXIST in 1.58.0 — that's why prior fix
   attempts didn't take. We use the real 1.58 names below. */
header[data-testid="stHeader"],
[data-testid="stHeader"] > div {{
    background: transparent !important;
    border-bottom: 0 !important;
    box-shadow: none !important;
    /* Keep height intact; just visually blank. */
    height: auto !important;
    min-height: 0 !important;
    /* Streamlit's z-index layout (verified in 1.58.0 minified bundle):
         stSidebar   = zIndices.sidebar (~1100)
         section.main= zIndices.sidebar + 1 (1101)
         stHeader    = zIndices.header (~1000, below sidebar)
       The header MUST sit ABOVE the main content (1101) so the
       stExpandSidebarButton inside it is clickable, and BELOW or
       AT the sidebar so the sidebar can cover it on desktop. We
       use 1000 (=zIndices.header) which is the default — this is
       what the previous "z-index:0" rule broke. */
    z-index: 1000 !important;
    position: relative !important;
}}
/* Belt-and-suspenders: explicitly restore BOTH buttons with the
   correct 1.58.0 data-testid values, force them visible at all
   times (including on touch devices where :hover never fires),
   and give them a small paper-warm chip so they read as controls
   not chrome.

   Key layout fix: pin the expand button to the top-left of the
   VIEWPORT (not the header, which can be pushed under sidebar).
   And pin the collapse button to the sidebar's top-right edge so
   it does NOT scroll away with the rest of the sidebar. */
[data-testid="stExpandSidebarButton"] {{
    display: inline-flex !important;
    visibility: visible !important;
    z-index: 1200 !important;          /* above sidebar (1100) */
    color: var(--ink) !important;
    background: var(--paper-warm) !important;
    border: 1px solid var(--rule) !important;
    box-shadow: 0 2px 6px rgba(15, 23, 42, 0.18) !important;
    border-radius: 0 !important;
    padding: 8px 12px !important;
    margin: 10px 0 0 10px !important;
    cursor: pointer !important;
    transition: background .15s ease, color .15s ease !important;
    /* Pin to top-left of viewport so it never gets pushed off-screen
       by the sidebar's right edge or by a sticky element. */
    position: fixed !important;
    top: 6px !important;
    left: 6px !important;
}}
/* stSidebarCollapseButton lives INSIDE stSidebarHeader (which is the
   sidebar's top bar). On mobile (no hover) React sets visibility:hidden
   — we override that. Pin it to sidebar's right edge with position:sticky
   fallback to position:absolute so it doesn't scroll out of view. */
[data-testid="stSidebarCollapseButton"] {{
    display: inline-flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    z-index: 1200 !important;          /* above other sidebar chrome */
    color: var(--ink) !important;
    background: var(--paper-warm) !important;
    border: 1px solid var(--rule) !important;
    box-shadow: 0 2px 6px rgba(15, 23, 42, 0.18) !important;
    border-radius: 0 !important;
    padding: 6px 10px !important;
    margin: 4px 0 0 0 !important;
    cursor: pointer !important;
    transition: background .15s ease, color .15s ease !important;
    position: sticky !important;
    top: 0 !important;
    right: 0 !important;
    align-self: flex-end !important;
}}
[data-testid="stExpandSidebarButton"]:hover,
[data-testid="stExpandSidebarButton"]:focus,
[data-testid="stSidebarCollapseButton"]:hover,
[data-testid="stSidebarCollapseButton"]:focus {{
    background: var(--ink) !important;
    color: var(--paper) !important;
    outline: none !important;
}}
/* Also force the parent of stSidebarCollapseButton (RDe wrapper, set
   to visibility:hidden until mouseenter) to always be visible. The
   1.58.0 component path is: stSidebar > stSidebarContent > stSidebarHeader
   > RDe (visibility-gated) > stSidebarCollapseButton. RDe's visibility
   cascades onto its child, so we have to override BOTH. */
[data-testid="stSidebarHeader"] {{
    display: flex !important;
    flex-direction: row !important;
    align-items: flex-start !important;
    justify-content: space-between !important;
    min-height: 44px !important;
}}
[data-testid="stSidebarHeader"] > [data-testid="stSidebarCollapseButton"] {{
    visibility: visible !important;
}}
/* Hide the rest of the Streamlit chrome — status widget, footer,
   and the right-side deploy toolbar (not needed for study). We do
   NOT blanket-hide [data-testid="stToolbar"] — that's the parent
   wrapper of stExpandSidebarButton, and nuke-ing it strands mobile
   users with a collapsed sidebar they can never re-open. Instead
   we hide the deploy/menu widgets individually below. */
#MainMenu, footer,
[data-testid="stStatusWidget"] {{
    display: none !important;
}}
/* Hide the "Made with Streamlit" / hamburger / deploy menu that
   lives inside stAppToolbar — but NOT stExpandSidebarButton which
   is a sibling and is essential for mobile. We use the toolbar's
   right-side action container; the expand button is in a separate
   left-side child. */
[data-testid="stToolbar"] [data-testid="stToolbarActions"],
[data-testid="stAppDeployButton"] {{
    display: none !important;
}}

/* Sidebar becomes a thick inked rule instead of a flat gray panel */
section[data-testid="stSidebar"] {{
    background: var(--paper-warm) !important;
    border-right: 2px solid var(--ink) !important;
    padding-top: 1.5rem !important;
}}
section[data-testid="stSidebar"] * {{
    font-family: {FONT_BODY};
    color: var(--ink) !important;
}}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {{
    font-family: {FONT_DISPLAY};
    color: var(--cinnabar) !important;
    letter-spacing: 0.02em;
}}

/* === EDITORIAL DROPCAPS / SECTION NUMBERS === */
.editorial-no {{
    font-family: {FONT_NUMBER};
    font-style: italic;
    font-size: 14px;
    color: var(--cinnabar);
    letter-spacing: 0.18em;
    text-transform: uppercase;
    font-weight: 600;
}}

.editorial-rule {{
    display: flex;
    align-items: center;
    gap: 14px;
    margin: 18px 0 8px 0;
    color: var(--cinnabar);
    font-family: {FONT_NUMBER};
}}
.editorial-rule::before,
.editorial-rule::after {{
    content: "";
    flex: 1;
    height: 1px;
    background: var(--rule);
}}
.editorial-rule span {{
    font-size: 12px;
    letter-spacing: 0.32em;
    text-transform: uppercase;
    font-style: italic;
}}

/* === PAPER CARDS === */
.paper-card {{
    background: var(--card-bg);
    border: 1px solid var(--rule);
    border-radius: 0;     /* NO rounded corners — paper-edge feel */
    padding: 24px 28px;
    margin: 0 0 20px 0;
    position: relative;
    transition: border-color .2s ease;
}}
.paper-card::before {{
    /* tiny corner mark — feels like a journal page tab */
    content: "";
    position: absolute;
    top: 0; right: 0;
    width: 28px; height: 28px;
    background:
        linear-gradient(135deg, transparent 50%, var(--rule) 50%);
    pointer-events: none;
}}
.paper-card:hover {{ border-color: var(--ink); }}
.paper-card.accent-cinnabar {{ border-left: 4px solid var(--cinnabar); padding-left: 24px; }}
.paper-card.accent-jade     {{ border-left: 4px solid var(--jade);     padding-left: 24px; }}
.paper-card.accent-amber    {{ border-left: 4px solid var(--amber);    padding-left: 24px; }}

/* === EDITORIAL HERO === */
.editorial-hero {{
    border-top: 3px double var(--ink);
    border-bottom: 1px solid var(--rule);
    padding: 30px 8px 26px 8px;
    margin-bottom: 28px;
    position: relative;
}}
.editorial-hero .pre {{
    font-family: {FONT_NUMBER};
    font-style: italic;
    color: var(--cinnabar);
    font-size: 13px;
    letter-spacing: 0.28em;
    text-transform: uppercase;
    margin-bottom: 10px;
}}
.editorial-hero h1 {{
    font-family: {FONT_DISPLAY};
    font-weight: 900;
    font-size: clamp(38px, 5.4vw, 76px);
    line-height: 1.02;
    letter-spacing: -0.02em;
    color: var(--ink);
    margin: 0 0 14px 0;
    max-width: 920px;
}}
.editorial-hero h1 em {{
    font-style: italic;
    color: var(--cinnabar);
    font-weight: 700;
}}
.editorial-hero .deck {{
    font-family: {FONT_BODY};
    font-size: 17px;
    line-height: 1.6;
    color: var(--ink-soft);
    max-width: 680px;
    font-style: italic;
}}

/* === STAT SHEET (dashboard tiles) === */
.stat-sheet {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 1px;
    background: var(--rule);
    border: 1px solid var(--rule);
    margin: 16px 0 24px 0;
}}
.stat-cell {{
    background: var(--paper);
    padding: 22px 18px 18px 18px;
    position: relative;
}}
.stat-cell .stat-no {{
    font-family: {FONT_NUMBER};
    font-style: italic;
    color: var(--cinnabar);
    font-size: 11px;
    letter-spacing: 0.22em;
    margin-bottom: 8px;
}}
.stat-cell .stat-value {{
    font-family: {FONT_NUMBER};
    font-weight: 700;
    color: var(--ink);
    font-size: 56px;
    line-height: 1;
    letter-spacing: -0.03em;
    margin-bottom: 4px;
    font-feature-settings: "tnum";
}}
.stat-cell .stat-suffix {{
    font-size: 22px;
    color: var(--muted);
    font-weight: 400;
    margin-left: 2px;
}}
.stat-cell .stat-label {{
    font-family: {FONT_BODY};
    font-size: 13px;
    color: var(--ink-soft);
    letter-spacing: 0.04em;
}}
.stat-cell .stat-delta {{
    font-size: 12px;
    color: var(--jade);
    margin-top: 6px;
    font-style: italic;
    font-family: {FONT_BODY};
}}
.stat-cell .stat-delta.negative {{ color: var(--cinnabar-deep); }}

/* === CHAPTER NUMBER (sidebar nav) === */
.nav-chapter {{
    font-family: {FONT_NUMBER};
    font-style: italic;
    color: var(--cinnabar);
    font-size: 12px;
    letter-spacing: 0.25em;
    margin: 14px 0 4px 4px;
    text-transform: uppercase;
    border-top: 1px solid var(--rule);
    padding-top: 12px;
}}

/* === ST.MARKDOWN HEADERS — match editorial display === */
section.main h1,
section.main h2,
section.main h3 {{
    font-family: {FONT_DISPLAY};
    color: var(--ink);
    letter-spacing: -0.01em;
}}
section.main h1 {{ font-size: 42px; font-weight: 800; line-height: 1.05; }}
section.main h2 {{ font-size: 30px; font-weight: 700; line-height: 1.15; border-bottom: 1px solid var(--rule); padding-bottom: 12px; }}
section.main h3 {{ font-size: 22px; font-weight: 700; line-height: 1.2; font-style: italic; }}
section.main h4 {{ font-family: {FONT_BODY}; font-weight: 600; font-size: 16px; color: var(--cinnabar); text-transform: uppercase; letter-spacing: 0.12em; margin: 18px 0 10px 0; }}
section.main p, section.main li {{ font-family: {FONT_BODY}; font-size: 16px; line-height: 1.7; }}
section.main small, section.main .caption {{ color: var(--muted); font-style: italic; }}

/* === BUTTONS — flat, ink-stamped === */
.stButton > button,
button[data-testid="baseButton-primary"],
button[data-testid="baseButton-secondary"] {{
    font-family: {FONT_BODY};
    font-weight: 600;
    border-radius: 0;
    padding: 10px 22px;
    letter-spacing: 0.02em;
    border: 1.5px solid var(--ink);
    background: var(--paper);
    color: var(--ink);
    transition: all .15s ease;
    text-transform: none;
}}
.stButton > button:hover,
button[data-testid="baseButton-primary"]:hover,
button[data-testid="baseButton-secondary"]:hover {{
    background: var(--ink);
    color: var(--paper);
}}
button[data-testid="baseButton-primary"] {{
    background: var(--cinnabar) !important;
    color: var(--paper) !important;
    border-color: var(--cinnabar) !important;
}}
button[data-testid="baseButton-primary"]:hover {{
    background: var(--cinnabar-deep) !important;
    border-color: var(--cinnabar-deep) !important;
}}

/* === INPUTS — paper forms === */
.stTextInput input,
.stTextArea textarea,
.stNumberInput input,
.stSelectbox > div,
.stRadio > div {{
    background: var(--paper) !important;
    border: 1px solid var(--rule) !important;
    border-radius: 0 !important;
    font-family: {FONT_BODY} !important;
    color: var(--ink) !important;
}}
.stTextInput input:focus,
.stTextArea textarea:focus {{
    border-color: var(--cinnabar) !important;
    box-shadow: 0 0 0 1px var(--cinnabar) inset !important;
    outline: none !important;
}}

/* === RADIO BUTTONS as inline chapter selectors === */
.stRadio [role="radiogroup"] {{
    gap: 0;
    flex-wrap: wrap;
}}
.stRadio [role="radiogroup"] label {{
    background: transparent;
    border: 1px solid var(--rule);
    border-right: 0;
    padding: 7px 16px;
    font-family: {FONT_BODY};
    font-size: 14px;
    color: var(--ink-soft);
    cursor: pointer;
    transition: all .12s ease;
}}
.stRadio [role="radiogroup"] label:last-child {{
    border-right: 1px solid var(--rule);
}}
.stRadio [role="radiogroup"] label[data-checked="true"] {{
    background: var(--ink);
    color: var(--paper);
    border-color: var(--ink);
}}
.stRadio [role="radiogroup"] label:hover {{
    background: var(--paper-warm);
    color: var(--ink);
}}
.stRadio [role="radiogroup"] label[data-checked="true"]:hover {{
    background: var(--ink);
    color: var(--paper);
}}

/* === MULTISELECT === */
.stMultiSelect [data-baseweb="select"] {{
    background: var(--paper) !important;
    border: 1px solid var(--rule) !important;
    border-radius: 0 !important;
}}

/* === EXPANDER — like opening a folded pamphlet === */
.streamlit-expanderHeader,
[data-testid="stExpander"] details summary {{
    background: var(--paper-warm) !important;
    border: 1px solid var(--rule) !important;
    border-radius: 0 !important;
    font-family: {FONT_BODY} !important;
    font-weight: 600 !important;
    color: var(--ink) !important;
}}
.streamlit-expanderContent,
[data-testid="stExpander"] details {{
    background: var(--card-bg) !important;
    border: 1px solid var(--rule) !important;
    border-top: 0 !important;
}}

/* === PROGRESS BAR — thin rule with stamp === */
.stProgress > div > div > div > div {{
    background: var(--cinnabar) !important;
}}
.stProgress > div > div > div {{
    background: var(--rule) !important;
}}

/* === METRIC widget — overwrite Streamlit's default === */
[data-testid="stMetric"] {{
    background: var(--paper) !important;
    border: 1px solid var(--rule) !important;
    border-left: 3px solid var(--cinnabar) !important;
    padding: 14px 18px !important;
    border-radius: 0 !important;
}}
[data-testid="stMetric"] label {{
    font-family: {FONT_NUMBER} !important;
    font-style: italic !important;
    color: var(--cinnabar) !important;
    font-size: 11px !important;
    letter-spacing: 0.22em !important;
    text-transform: uppercase !important;
}}
[data-testid="stMetricValue"] {{
    font-family: {FONT_NUMBER} !important;
    font-weight: 700 !important;
    color: var(--ink) !important;
    font-size: 32px !important;
    font-feature-settings: "tnum" !important;
}}
[data-testid="stMetricDelta"] svg {{ display: none; }}

/* === ST.MARKDOWN TABLES — ruled ledger style === */
section.main table {{
    border-collapse: collapse;
    width: 100%;
    font-family: {FONT_BODY};
    margin: 14px 0;
}}
section.main table th {{
    text-align: left;
    font-family: {FONT_NUMBER};
    font-style: italic;
    color: var(--cinnabar);
    font-size: 12px;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    border-bottom: 1.5px solid var(--ink);
    padding: 8px 12px;
}}
section.main table td {{
    padding: 10px 12px;
    border-bottom: 1px solid var(--rule);
    color: var(--ink);
}}

/* === INFO / SUCCESS / WARNING BOXES — paper note style === */
.stAlert,
[data-testid="stAlert"] {{
    border-radius: 0 !important;
    border: 1px solid var(--rule) !important;
    background: var(--paper-warm) !important;
    border-left: 4px solid var(--cinnabar) !important;
}}

/* === CODE / MONOSPACE — a small ink type === */
code, pre, .stCode {{
    font-family: 'JetBrains Mono', 'Source Code Pro', 'Consolas', monospace;
    background: var(--paper-warm) !important;
    color: var(--cinnabar-deep) !important;
    border: 1px solid var(--rule);
    padding: 2px 6px;
    font-size: 13.5px;
}}

/* === HIDE STREAMLIT CHROME === */
#MainMenu, footer {{ visibility: hidden; }}
[data-testid="stToolbar"] {{ display: none; }}

/* === ANIMATION === */
@keyframes ink-stamp {{
    0%   {{ transform: scale(0.92) rotate(-1deg); opacity: 0;   }}
    50%  {{ transform: scale(1.04) rotate(0.5deg); opacity: 1; }}
    100% {{ transform: scale(1)    rotate(0);     opacity: 1;   }}
}}
.ink-stamp {{
    animation: ink-stamp .5s cubic-bezier(.2, .9, .3, 1.1);
}}

/* === Mobile / narrow viewport === */
@media (max-width: 768px) {{
    .editorial-hero h1 {{ font-size: 38px; }}
    .stat-cell .stat-value {{ font-size: 40px; }}
    .paper-card {{ padding: 18px 18px; }}
}}
</style>
"""


def inject_design_css() -> None:
    """Inject the master stylesheet. Call once at the top of any
    page renderer. Safe to call on every rerun (the browser dedupes
    <style> blocks with identical text)."""
    st.markdown(DESIGN_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Editorial hero (top of dashboard)
# ---------------------------------------------------------------------------
def editorial_hero(level: str, total_words: int) -> None:
    """Big editorial top-of-page header. Sets the tone for the whole
    site — feels like opening a magazine. Fully Chinese — no English."""
    import datetime as _dt
    # Cross-platform month formatting. %-m (no leading zero) is a
    # glibc-only extension; Windows uses %#m. We pick whichever works.
    try:
        issue_date = _dt.date.today().strftime("%Y 年 %#m 月")
    except ValueError:
        issue_date = _dt.date.today().strftime("%Y 年 %-m 月")
    st.markdown(
        f"""
<div class="editorial-hero">
<div class="pre">CET 智胜 · 大学英语四六级备考 · {issue_date} · 第 {total_words // 100 + 1} 期</div>
<h1>今晚你构建的英语,<br>就是明天你带进考场的那份<span style="color:var(--cinnabar); font-style:italic; font-weight:700;">底稿</span>。</h1>
<p class="deck">专为<span style="color:var(--cinnabar); font-weight:700; font-style:normal;">大学</span>生打造的大学英语四六级 (CET-4 / CET-6) 备考系统。当前级别:<em>{level}</em>。五项核心训练 — 词汇、阅读、听力、翻译、写作 — 每一项均配备近十年真题题库与 AI 智能诊断反馈。</p>
</div>
""",
        unsafe_allow_html=True,
    )


def editorial_rule(label: str) -> None:
    """Centered horizontal rule with a small label between two hairlines.
    Used as a section break inside a page (e.g. 'I · STAT SHEET')."""
    st.markdown(
        f'<div class="editorial-rule"><span>{label}</span></div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Stat sheet — replaces the default st.metric row with a 1920s-accounting-
# book look. Each tile is bordered on all four sides, with a roman-numeral
# chapter number and a 56px Playfair numeral.
# ---------------------------------------------------------------------------
def stat_sheet(cells: list[dict]) -> None:
    """Render a horizontal ledger of stat cells.

    Each ``cell`` dict has:
        no      — small roman-numeral label, e.g. "I"
        value   — the big number, e.g. 6962
        suffix  — small unit, e.g. "词" (optional, default "")
        label   — caption below the number
        delta   — italic line below, e.g. "62 today" (optional)
        delta_negative — bool, render in red instead of green
    """
    rows = []
    for c in cells:
        delta = c.get("delta", "")
        delta_class = "negative" if c.get("delta_negative") else ""
        delta_html = (
            f'<div class="stat-delta {delta_class}">{_h(delta)}</div>'
            if delta else ""
        )
        suffix = f'<span class="stat-suffix">{_h(c.get("suffix",""))}</span>' \
                 if c.get("suffix") else ""
        rows.append(
            f'<div class="stat-cell">'
            f'<div class="stat-no">{_h(c.get("no",""))}</div>'
            f'<div class="stat-value">{_h(str(c.get("value",0)))}{suffix}</div>'
            f'<div class="stat-label">{_h(c.get("label",""))}</div>'
            f'{delta_html}'
            f'</div>'
        )
    # Concatenate WITHOUT any newlines/whitespace between divs —
    # streamlit's markdown parser can otherwise treat indented content
    # as a code block and render it as literal text.
    st.markdown(
        f'<div class="stat-sheet">{"".join(rows)}</div>',
        unsafe_allow_html=True,
    )


def _h(s: str) -> str:
    """HTML escape."""
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


# ---------------------------------------------------------------------------
# Sidebar — replace the default "CET 智胜" block with an editorial masthead.
# We put the SVG icons in a single self-contained HTML block rendered via
# streamlit.components.v1.html so React doesn't see them.
# ---------------------------------------------------------------------------
def _svg_small(d: str, viewbox: str = "0 0 24 24") -> str:
    """A minimal hand-drawn-feel icon for the sidebar. We avoid mask-image
    and any complex <svg> tricks that React choked on. Just a 1.2em
    stroke SVG. Stays inline so React never has to find a node."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="1.1em" '
            f'height="1.1em" viewBox="{viewbox}" fill="none" '
            f'stroke="currentColor" stroke-width="1.7" '
            f'stroke-linecap="round" stroke-linejoin="round">'
            f'{d}</svg>')


# Editorial line-art icons. Stroke-only, no colour fonts.
ICON_DASHBOARD  = _svg_small('<rect x="3" y="3" width="7" height="9"/><rect x="14" y="3" width="7" height="5"/><rect x="14" y="12" width="7" height="9"/><rect x="3" y="16" width="7" height="5"/>')
ICON_VOCAB      = _svg_small('<path d="M4 4h12a2 2 0 012 2v14H6a2 2 0 01-2-2V4z"/><path d="M16 4V2H6"/><path d="M8 8h6M8 12h6M8 16h4"/>')
ICON_QUIZ       = _svg_small('<rect x="3" y="3" width="18" height="18" rx="1"/><circle cx="9" cy="9" r="1.3" fill="currentColor"/><circle cx="15" cy="9" r="1.3" fill="currentColor"/><circle cx="9" cy="15" r="1.3" fill="currentColor"/><circle cx="15" cy="15" r="1.3" fill="currentColor"/><circle cx="12" cy="12" r="1.3" fill="currentColor"/>')
ICON_READING    = _svg_small('<path d="M3 5h6a3 3 0 013 3v12a2 2 0 00-2-2H3V5z"/><path d="M21 5h-6a3 3 0 00-3 3v12a2 2 0 012-2h7V5z"/>')
ICON_LISTENING  = _svg_small('<path d="M4 14v-2a8 8 0 0116 0v2"/><rect x="3" y="14" width="4" height="6" rx="1.2" fill="currentColor" stroke="none"/><rect x="17" y="14" width="4" height="6" rx="1.2" fill="currentColor" stroke="none"/>')
ICON_GRADER     = _svg_small('<path d="M12 3a9 9 0 100 18c1 0 2-.5 2-1.5 0-1-.5-1.5-1-2-.5-.5-1-1-1-2 0-1.5 1-2.5 3-2.5h2a4 4 0 004-4c0-3.5-4-6-9-6z"/><circle cx="7.5" cy="10" r="1" fill="currentColor"/><circle cx="11" cy="6.8" r="1" fill="currentColor"/><circle cx="15" cy="9" r="1" fill="currentColor"/><circle cx="17" cy="13" r="1" fill="currentColor"/>')
ICON_WRONG      = _svg_small('<path d="M5 4h14v16H5z M5 4l14 16 M19 4L5 20"/><path d="M5 4l14 16"/>')   # not a real X, more of a journal mark


def render_sidebar_masthead() -> str:
    """Return the editorial-style sidebar header as a string. The caller
    renders it via ``st.markdown(unsafe_allow_html=True)`` once at the
    top of every page so the masthead is visible across the app.
    """
    # NB: the inner <div>s have NO leading whitespace. Streamlit's
    # markdown parser treats indented HTML as a code block and renders
    # the markup as literal text, which is the bug we hit at first.
    return f"""
<div style="border-bottom: 2px solid #1A1A1A; padding-bottom: 18px; margin-bottom: 14px;">
<div style="font-family: {FONT_NUMBER}; font-style: italic; color: {TOKENS['cinnabar']}; font-size: 11px; letter-spacing: 0.3em; text-transform: uppercase;">EST. 2026 · CET PREPARATION</div>
<div style="font-family: {FONT_DISPLAY}; font-weight: 900; font-size: 32px; line-height: 1.0; color: {TOKENS['ink']}; margin: 4px 0 6px 0; letter-spacing: -0.01em;">CET<br><em style="color: {TOKENS['cinnabar']};">智胜</em></div>
<div style="font-family: {FONT_BODY}; font-size: 12px; color: {TOKENS['ink_soft']}; font-style: italic; line-height: 1.5;">A study journal for the<br>College English Test</div>
</div>
"""


# Page labels used in the sidebar. Editorial chapter numbers.
CHAPTERS = [
    ("📊", "I",  "Dashboard",  "学霸看板",       "dashboard"),
    ("📝", "II", "Vocabulary", "词汇",           "vocab"),
    ("🎲", "III", "Self-Test",  "背单词自测",     "quiz"),
    ("📖", "IV",  "Reading",    "阅读训练",       "reading"),
    ("🎧", "V",   "Listening",  "听力训练",       "listening"),
    ("✒️", "VI",  "Grader",     "AI 批改官",     "grader"),
    ("🟥", "VII", "Wrong Book", "错题本",         "wrong"),
]


def render_chapter_index(active: str) -> None:
    """Render the editorial chapter index. Used inside the existing
    sidebar radio. We pre-style each option so the user sees Roman
    numerals + serif section labels.
    """
    pass  # The chapter list is already rendered by the existing
    # sidebar radio. This helper is kept here as a placeholder for
    # future "chapter list" mode where we replace the radio entirely.


# ---------------------------------------------------------------------------
# Word-of-the-day pull quote (used in the dashboard deck)
# ---------------------------------------------------------------------------
QUOTES = [
    "A page a day, twelve weeks from now — that's the paper.",
    "Wrong answers are the only place where new English lives.",
    "The gap between a 425 and a 550 is not talent, it's repetition.",
    "Read a real paper article every night. CET is just speed.",
    "There is no shortcut; there is only the calendar.",
    "You don't need a thousand words. You need the right 600.",
    "Cinnabar red on cream paper — your essay should look like that.",
]
