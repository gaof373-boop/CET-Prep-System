"""📱 CET 智胜 · Kivy 手机 App 独立入口

【架构原则】
    1. 绝对隔离: 不 import ui.views / web_app / tkinter / streamlit
    2. 业务复用: 直接 import core.data_manager / core.ai_service
       → 桌面版 + 网页版的 SQLite 查询、AI 调用、生词捕捉逻辑
         100% 复用,手机 App 只负责"换皮"
    3. 移动优先:  Kivy 原生 BoxLayout/ScreenManager,单手竖屏交互

【手机端三屏架构】
    Screen 1 (DashboardScreen)  : 学霸数据看板  2x2 大数字 + 鼓励标语
    Screen 2 (VocabScreen)      : 词汇自测 + 单词点击查词
    Screen 3 (AIGraderScreen)   : 写作 / 翻译 精批,大 TextEdit 适配软键盘

【启动方式】
    cd D:\\CET-Prep-System
    python mobile_main.py
    # 弹出 360x640 模拟手机窗口,可在 Windows 桌面上滑动切换三屏
"""

from __future__ import annotations

import os
import random
import sys
from pathlib import Path

# CRITICAL: chdir to project root BEFORE importing core.*,
# so the main DB at <root>/database/cet_exam.db is always found.
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

# Kivy config BEFORE importing App — use SDL2 to avoid ANGLE / D3D issues
os.environ.setdefault("KIVY_NO_ARGS", "1")
os.environ.setdefault("KIVY_NO_CONSOLELOG", "0")

import kivy  # noqa: E402
from kivy.config import Config  # noqa: E402

# Simulate a phone-portrait window. The user can resize freely.
Config.set("graphics", "width", "390")        # iPhone 14 logical width
Config.set("graphics", "height", "780")       # 16:9-ish portrait
Config.set("graphics", "resizable", "1")
Config.set("input", "mouse", "mouse,multitouch_on_demand")
Config.set("kivy", "log_level", "info")

# Kivy < 2.0 needs this; harmless on 2.x
kivy.require("2.3.0")

from kivy.app import App  # noqa: E402
from kivy.clock import Clock  # noqa: E402
from kivy.core.window import Window  # noqa: E402
from kivy.metrics import dp, sp  # noqa: E402
from kivy.properties import (  # noqa: E402
    ListProperty, NumericProperty, ObjectProperty, StringProperty,
)
from kivy.uix.boxlayout import BoxLayout  # noqa: E402
from kivy.uix.button import Button  # noqa: E402
from kivy.uix.floatlayout import FloatLayout  # noqa: E402
from kivy.uix.label import Label  # noqa: E402
from kivy.uix.popup import Popup  # noqa: E402
from kivy.uix.screenmanager import Screen, ScreenManager  # noqa: E402
from kivy.uix.scrollview import ScrollView  # noqa: E402
from kivy.uix.textinput import TextInput  # noqa: E402
from kivy.uix.widget import Widget  # noqa: E402

# ---- Reuse the desktop / web app's data + AI layer ----
from core.data_manager import DataManager  # noqa: E402
from core.ai_service import AIService  # noqa: E402
from core.db_init import DB_PATH, init_database  # noqa: E402

# Make sure schema exists (no-op on subsequent runs)
init_database()

# ---- Theme palette (single source of truth, mirrors web_app.py) ----
THEME = {
    "bg":       [0.95, 0.97, 0.99, 1],   # near-white
    "card":     [1, 1, 1, 1],
    "ink":      [0.06, 0.09, 0.16, 1],
    "muted":    [0.42, 0.45, 0.50, 1],
    "green":    [0.06, 0.72, 0.51, 1],   # mastered
    "red":      [0.94, 0.27, 0.27, 1],   # wrong
    "blue":     [0.23, 0.51, 0.96, 1],   # practice
    "purple":   [0.55, 0.36, 0.96, 1],   # AI
    "amber":    [0.96, 0.62, 0.04, 1],   # warning
    "border":   [0.85, 0.88, 0.93, 1],
    "primary":  [0.23, 0.51, 0.96, 1],
    "primary_d":[0.15, 0.39, 0.82, 1],
}

QUOTES = [
    "今天也是充满斗志的一天!你已累计在系统内斩落 {n} 个核心考点。",
    "水滴石穿,绳锯木断。再小的进步,都是通往 600+ 路上的真金白银。",
    "英语学习没有速成,只有每天 30 分钟的坚持。",
    "不怕慢,只怕站。今天你比昨天多记 5 个词,12 月考场你就会多 5 分底气。",
    "CET 不是天赋的较量,是习惯的较量 — 系统陪你把习惯刻进日历。",
    "你不需要完美,你只需要今天比昨天多坚持 10 分钟。",
    "错题本不是伤疤,是勋章 — 每一道你不再错的题,都是勋章上的一颗星。",
]


# ===========================================================================
# Reusable building blocks
# ===========================================================================
class StatCard(BoxLayout):
    """A single 2x2 stat card.

    Layout: [ accent bar | big number | label / hint ]
    Used on the dashboard. Touching the card triggers ``on_press`` if set.
    """
    accent = ListProperty(THEME["blue"])
    big_value = StringProperty("—")
    label = StringProperty("")
    hint = StringProperty("")

    def __init__(self, accent, value, label, hint="", on_press=None, **kw):
        super().__init__(**kw)
        self.orientation = "vertical"
        self.padding = [dp(14), dp(14), dp(14), dp(14)]
        self.spacing = dp(2)
        self.size_hint_y = None
        self.height = dp(120)
        self.accent = accent
        # background
        with self.canvas.before:
            from kivy.graphics import Color, RoundedRectangle
            Color(*THEME["card"])
            self._bg_rect = RoundedRectangle(
                pos=self.pos, size=self.size, radius=[dp(12)]
            )
            Color(*self.accent)
            self._accent_rect = RoundedRectangle(
                pos=self.pos, size=(dp(4), self.size[1]), radius=[dp(2)]
            )
        self.bind(pos=self._update_bg, size=self._update_bg)

        # --- inner labels (build BEFORE assigning to StringProperty
        # so on_* handlers don't fire with missing attributes) ---
        self._v = Label(
            text="", color=self.accent,
            font_size=sp(32), bold=True,
            halign="left", valign="middle",
            size_hint_y=None, height=dp(46),
        )
        self._l = Label(
            text="", color=THEME["ink"],
            font_size=sp(13), bold=True,
            halign="left", valign="middle",
            size_hint_y=None, height=dp(20),
        )
        self._h = Label(
            text="", color=THEME["muted"],
            font_size=sp(10),
            halign="left", valign="middle",
            size_hint_y=None, height=dp(20),
        )
        self.add_widget(self._v)
        self.add_widget(self._l)
        self.add_widget(self._h)

        # Now safe to assign — handlers will update the labels
        self.big_value = value
        self.label = label
        self.hint = hint

        if on_press is not None:
            self._on_press_cb = on_press

    def _update_bg(self, *_):
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size
        # accent strip is 4px on the left
        self._accent_rect.pos = self.pos
        self._accent_rect.size = (dp(4), self.size[1])

    def on_big_value(self, *_):
        self._v.text = self.big_value

    def on_label(self, *_):
        self._l.text = self.label

    def on_hint(self, *_):
        self._h.text = self.hint

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos) and getattr(self, "_on_press_cb", None):
            self._on_press_cb()
            return True
        return super().on_touch_down(touch)


class TopBar(BoxLayout):
    """Sticky top bar: title + level pill."""
    title = StringProperty("CET 智胜")
    level = StringProperty("CET-4")

    def __init__(self, title, level="CET-4", **kw):
        super().__init__(**kw)
        self.orientation = "horizontal"
        self.size_hint_y = None
        self.height = dp(52)
        self.padding = [dp(16), dp(8), dp(16), dp(8)]
        self.spacing = dp(8)
        with self.canvas.before:
            from kivy.graphics import Color, Rectangle
            Color(*THEME["primary"])
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._sync, size=self._sync)
        self.title = title
        self.level = level
        self.add_widget(Label(
            text=f"📱  {self.title}", color=[1, 1, 1, 1],
            font_size=sp(16), bold=True,
            halign="left", valign="middle",
            size_hint_x=0.7,
        ))
        self._lvl = Label(
            text=f"📚 {self.level}", color=[1, 1, 1, 1],
            font_size=sp(12), bold=True,
            halign="right", valign="middle",
            size_hint_x=0.3,
        )
        self.add_widget(self._lvl)

    def _sync(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size

    def set_level(self, level: str):
        self.level = level
        self._lvl.text = f"📚 {level}"


class BottomNav(BoxLayout):
    """Three-tab bottom navigation: 看板 / 词汇 / AI 批改.

    Each tab is a tappable button. The active tab is highlighted.
    """
    active = StringProperty("dashboard")
    on_switch = ObjectProperty(lambda *_a, **_k: None)

    _TABS = [
        ("dashboard",   "📊", "看板"),
        ("vocab",       "📝", "词汇"),
        ("ai",          "🤖", "AI"),
    ]

    def __init__(self, on_switch, **kw):
        super().__init__(**kw)
        self.on_switch = on_switch
        self.orientation = "horizontal"
        self.size_hint_y = None
        self.height = dp(56)
        self.padding = [dp(4), dp(4), dp(4), dp(4)]
        self.spacing = dp(4)
        with self.canvas.before:
            from kivy.graphics import Color, Rectangle
            Color(*THEME["card"])
            self._bg = Rectangle(pos=self.pos, size=self.size)
            Color(*THEME["border"])
            self._top_line = Rectangle(
                pos=(self.x, self.top - dp(1)),
                size=(self.width, dp(1)),
            )
        self.bind(pos=self._sync, size=self._sync)
        self._buttons: dict[str, Button] = {}
        for key, icon, label in self._TABS:
            btn = Button(
                text=f"{icon}\n{label}",
                background_color=[0, 0, 0, 0],
                color=THEME["muted"],
                font_size=sp(12),
                halign="center", valign="middle",
            )
            btn.bind(on_release=lambda _b, k=key: self._on_tab(k))
            self._buttons[key] = btn
            self.add_widget(btn)
        self._refresh_active()

    def _sync(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._top_line.pos = (self.x, self.top - dp(1))
        self._top_line.size = (self.width, dp(1))

    def _on_tab(self, key: str):
        self.active = key
        self._refresh_active()
        self.on_switch(key)

    def _refresh_active(self):
        for k, btn in self._buttons.items():
            if k == self.active:
                btn.color = THEME["primary"]
            else:
                btn.color = THEME["muted"]

    def set_active(self, key: str):
        self.active = key
        self._refresh_active()


# ===========================================================================
# Screen 1: Dashboard
# ===========================================================================
class DashboardScreen(Screen):
    def __init__(self, dm: DataManager, on_switch_section=None, **kw):
        super().__init__(**kw)
        self.dm = dm
        self._on_switch_section = on_switch_section or (lambda _k: None)
        root = BoxLayout(orientation="vertical")
        root.add_widget(TopBar("学霸看板", level="CET-4"))

        # scrollable body
        scroll = ScrollView(size_hint=(1, 1))
        body = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            padding=[dp(16), dp(16), dp(16), dp(16)],
            spacing=dp(12),
        )
        body.bind(minimum_height=body.setter("height"))

        # ----- header / hero -----
        hero = BoxLayout(orientation="vertical", size_hint_y=None,
                          height=dp(72), spacing=dp(4))
        hero.add_widget(Label(
            text="📊 学霸备考数据看板",
            font_size=sp(22), bold=True, color=THEME["ink"],
            halign="left", valign="middle",
            size_hint_y=None, height=dp(34),
        ))
        hero.add_widget(Label(
            text="你的今日战况 · 4 大核心战报",
            font_size=sp(12), color=THEME["muted"],
            halign="left", valign="middle",
            size_hint_y=None, height=dp(20),
        ))
        body.add_widget(hero)

        # ----- 2x2 grid of stat cards -----
        self._card_mastered = StatCard(THEME["green"], "—", "🎯 已掌握词汇",
                                        "点击「词汇」标记 ✓")
        self._card_wrong = StatCard(THEME["red"], "—", "🟥 错题攻坚",
                                     "去「错题本」巩固")
        self._card_practice = StatCard(THEME["blue"], "—", "📚 刷题成就",
                                        "阅读 + 听力总题数")
        self._card_ai = StatCard(THEME["purple"], "—", "🤖 AI 助攻频次",
                                  "写作 + 翻译批改")

        row1 = BoxLayout(orientation="horizontal", size_hint_y=None,
                          height=dp(120), spacing=dp(10))
        row1.add_widget(self._card_mastered)
        row1.add_widget(self._card_wrong)
        body.add_widget(row1)

        row2 = BoxLayout(orientation="horizontal", size_hint_y=None,
                          height=dp(120), spacing=dp(10))
        row2.add_widget(self._card_practice)
        row2.add_widget(self._card_ai)
        body.add_widget(row2)

        # ----- motto quote -----
        self._quote = Label(
            text="", font_size=sp(13), italic=True,
            color=THEME["primary"],
            halign="center", valign="middle",
            size_hint_y=None, height=dp(60),
            text_size=(0, dp(60)),
        )
        body.add_widget(self._quote)

        # ----- quick actions -----
        actions = BoxLayout(orientation="vertical", size_hint_y=None,
                             height=dp(110), spacing=dp(8))
        actions.add_widget(Button(
            text="📝  开始背单词自测",
            font_size=sp(14), bold=True,
            background_color=THEME["primary"],
            color=[1, 1, 1, 1],
            on_release=lambda *_a: self._on_switch_section("vocab"),
        ))
        actions.add_widget(Button(
            text="🔄  刷新数据",
            font_size=sp(12),
            background_color=THEME["card"],
            color=THEME["muted"],
            on_release=lambda *_a: self.refresh(),
        ))
        body.add_widget(actions)

        scroll.add_widget(body)
        root.add_widget(scroll)
        self.add_widget(root)
        Clock.schedule_once(lambda _dt: self.refresh(), 0)

    def refresh(self):
        try:
            stats = self.dm.dashboard_stats()
            self._card_mastered.big_value = f"{stats['mastered']:,}"
            self._card_wrong.big_value = f"{stats['wrong_book']:,}"
            self._card_practice.big_value = f"{stats['practice_reading'] + stats['practice_listening']:,}"
            self._card_ai.big_value = f"{stats['ai_essay_grades'] + stats['ai_trans_grades']:,}"
            quote = random.choice(QUOTES).format(n=stats["total_words"])
            self._quote.text = f"💪 {quote}"
        except Exception as exc:  # pragma: no cover
            self._quote.text = f"(加载失败: {exc})"


# ===========================================================================
# Screen 2: Vocab (self-test + click-to-lookup)
# ===========================================================================
class VocabScreen(Screen):
    """A long-press / tap card to see translation popup."""

    def __init__(self, dm: DataManager, **kw):
        super().__init__(**kw)
        self.dm = dm
        self._current = None
        self._direction = "en_to_zh"
        self._revealed = False
        root = BoxLayout(orientation="vertical")
        root.add_widget(TopBar("词汇自测", level="CET-4"))

        # direction toggle
        bar = BoxLayout(orientation="horizontal", size_hint_y=None,
                         height=dp(40), padding=[dp(16), 4, dp(16), 4],
                         spacing=dp(8))
        self._btn_en2zh = Button(
            text="英 → 中", font_size=sp(12), bold=True,
            background_color=THEME["primary"], color=[1, 1, 1, 1],
            on_release=lambda *_a: self._set_direction("en_to_zh"),
        )
        self._btn_zh2en = Button(
            text="中 → 英", font_size=sp(12),
            background_color=THEME["card"], color=THEME["ink"],
            on_release=lambda *_a: self._set_direction("zh_to_en"),
        )
        bar.add_widget(self._btn_en2zh)
        bar.add_widget(self._btn_zh2en)
        root.add_widget(bar)

        # main card area
        body = BoxLayout(orientation="vertical",
                          padding=[dp(16), dp(8), dp(16), dp(16)],
                          spacing=dp(12))

        # big prompt card
        with body.canvas.before:
            from kivy.graphics import Color, RoundedRectangle
            Color(*THEME["card"])
            self._card_bg = RoundedRectangle(
                pos=body.pos, size=body.size, radius=[dp(12)]
            )
        body.bind(pos=self._sync_card_bg, size=self._sync_card_bg)
        self._prompt = Label(
            text="点击下方「🎯 抽一题」开始",
            font_size=sp(20), bold=True, color=THEME["ink"],
            halign="center", valign="middle",
            text_size=(Window.width - dp(64), dp(200)),
        )
        self._prompt.bind(size=lambda *_a: setattr(
            self._prompt, "text_size",
            (self._prompt.width, self._prompt.height),
        ))
        body.add_widget(self._prompt)

        # answer reveal area
        self._answer_lbl = Label(
            text="", font_size=sp(16), color=THEME["green"],
            halign="center", valign="middle",
            size_hint_y=None, height=dp(40),
        )
        body.add_widget(self._answer_lbl)

        # meta
        self._meta_lbl = Label(
            text="", font_size=sp(11), color=THEME["muted"],
            halign="center", valign="middle",
            size_hint_y=None, height=dp(20),
        )
        body.add_widget(self._meta_lbl)

        # buttons
        btn_row = BoxLayout(orientation="horizontal",
                             size_hint_y=None, height=dp(44),
                             spacing=dp(8))
        btn_row.add_widget(Button(
            text="🎯 抽一题", font_size=sp(13), bold=True,
            background_color=THEME["primary"], color=[1, 1, 1, 1],
            on_release=lambda *_a: self._next(),
        ))
        btn_row.add_widget(Button(
            text="🔓 显示答案", font_size=sp(12),
            background_color=THEME["card"], color=THEME["ink"],
            on_release=lambda *_a: self._reveal(),
        ))
        body.add_widget(btn_row)

        btn_row2 = BoxLayout(orientation="horizontal",
                              size_hint_y=None, height=dp(40),
                              spacing=dp(8))
        btn_row2.add_widget(Button(
            text="✅ 我答对了", font_size=sp(12), bold=True,
            background_color=THEME["green"], color=[1, 1, 1, 1],
            on_release=lambda *_a: self._mark(True),
        ))
        btn_row2.add_widget(Button(
            text="❌ 我答错了", font_size=sp(12), bold=True,
            background_color=THEME["red"], color=[1, 1, 1, 1],
            on_release=lambda *_a: self._mark(False),
        ))
        body.add_widget(btn_row2)

        # click-to-lookup hint
        body.add_widget(Label(
            text="💡 长按 / 点击下方词条可弹窗显示完整释义",
            font_size=sp(10), color=THEME["muted"],
            halign="center", valign="middle",
            size_hint_y=None, height=dp(20),
        ))

        # recent words strip — each tappable to popup
        scroll = ScrollView(size_hint_y=0.5)
        self._strip = BoxLayout(orientation="vertical", size_hint_y=None,
                                 spacing=dp(4), padding=[0, 4, 0, 4])
        self._strip.bind(minimum_height=self._strip.setter("height"))
        scroll.add_widget(self._strip)
        body.add_widget(scroll)

        root.add_widget(body)
        self.add_widget(root)

    def _sync_card_bg(self, *_):
        self._card_bg.pos = self.pos
        self._card_bg.size = self.size

    def _set_direction(self, d: str):
        self._direction = d
        if d == "en_to_zh":
            self._btn_en2zh.background_color = THEME["primary"]
            self._btn_en2zh.color = [1, 1, 1, 1]
            self._btn_zh2en.background_color = THEME["card"]
            self._btn_zh2en.color = THEME["ink"]
        else:
            self._btn_zh2en.background_color = THEME["primary"]
            self._btn_zh2en.color = [1, 1, 1, 1]
            self._btn_en2zh.background_color = THEME["card"]
            self._btn_en2zh.color = THEME["ink"]

    def _next(self):
        try:
            pool = self.dm.list_vocabulary("CET4", min_star=1)
            if not pool:
                self._prompt.text = "(词库为空)"
                return
            import random as _r
            self._current = _r.choice(pool)
            self._revealed = False
            self._answer_lbl.text = ""
            if self._direction == "en_to_zh":
                self._prompt.text = self._current.get("word", "")
            else:
                self._prompt.text = self._current.get("translation") or "(无中文)"
            self._meta_lbl.text = f"⭐ {self._current.get('star_rating', 0)} · 频率 {self._current.get('frequency', 0)}"
        except Exception as exc:
            self._prompt.text = f"(抽题失败: {exc})"

    def _reveal(self):
        if not self._current:
            return
        self._revealed = True
        if self._direction == "en_to_zh":
            self._answer_lbl.text = self._current.get("translation") or "(无中文释义)"
        else:
            self._answer_lbl.text = self._current.get("word", "")

    def _mark(self, correct: bool):
        if not self._current:
            return
        try:
            if correct:
                self.dm.record_correct(self._current["id"])
            else:
                self.dm.record_wrong(self._current["id"])
        except Exception:
            pass
        self._answer_lbl.text = "✓ 已记录" if correct else "✗ 已加入错题本"
        # schedule next
        Clock.schedule_once(lambda _dt: self._next(), 0.6)

    def on_enter(self):
        # Populate the tappable word strip on first entry
        if not self._strip.children:
            Clock.schedule_once(lambda _dt: self._populate_strip(), 0)

    def _populate_strip(self):
        try:
            rows = self.dm.list_vocabulary("CET4", min_star=1)[:30]
        except Exception:
            return
        for r in rows:
            row = BoxLayout(orientation="horizontal", size_hint_y=None,
                            height=dp(36), padding=[dp(8), 2, dp(8), 2])
            word = r.get("word", "")
            trans = r.get("translation", "") or "(暂无)"
            star = r.get("star_rating", 0)
            btn = Button(
                text=f"{word}   ·   {trans}   ⭐{star}",
                font_size=sp(12),
                background_color=THEME["card"],
                color=THEME["ink"],
                halign="left", valign="middle",
                size_hint_y=None, height=dp(36),
            )
            btn.bind(on_release=lambda _b, w=word, t=trans, s=star:
                     self._show_lookup(w, t, s))
            self._strip.add_widget(row)
            row.add_widget(btn)

    def _show_lookup(self, word: str, trans: str, star: int):
        """Click-to-lookup popup — shows full translation, phonetic, etc."""
        try:
            row = self.dm.get_word_by_id(0)  # we need a helper, fall through
        except Exception:
            pass
        content = BoxLayout(orientation="vertical", padding=dp(12),
                             spacing=dp(6))
        content.add_widget(Label(
            text=word, font_size=sp(22), bold=True,
            color=THEME["ink"], size_hint_y=None, height=dp(40),
        ))
        content.add_widget(Label(
            text=trans, font_size=sp(14), color=THEME["green"],
            size_hint_y=None, height=dp(28),
        ))
        content.add_widget(Label(
            text=f"⭐ 星级 {star}", font_size=sp(11), color=THEME["muted"],
            size_hint_y=None, height=dp(20),
        ))
        # catch button
        catch_btn = Button(
            text="➕ 加入错题本", font_size=sp(13), bold=True,
            background_color=THEME["red"], color=[1, 1, 1, 1],
            size_hint_y=None, height=dp(40),
        )
        content.add_widget(catch_btn)
        close_btn = Button(
            text="关闭", font_size=sp(12),
            background_color=THEME["card"], color=THEME["ink"],
            size_hint_y=None, height=dp(36),
        )
        content.add_widget(close_btn)
        popup = Popup(title=f"🔍  {word}", content=content,
                       size_hint=(0.85, 0.55), auto_dismiss=True)

        def on_catch(*_):
            try:
                self.dm.add_word_to_wrong_book(
                    word, level="CET4",
                    translation=trans, source="mobile_lookup",
                )
            except Exception:
                pass
            catch_btn.text = "✓ 已加入"
            catch_btn.background_color = THEME["green"]

        catch_btn.bind(on_release=on_catch)
        close_btn.bind(on_release=popup.dismiss)
        popup.open()


# ===========================================================================
# Screen 3: AI Grader
# ===========================================================================
class AIGraderScreen(Screen):
    def __init__(self, dm: DataManager, ai: AIService, **kw):
        super().__init__(**kw)
        self.dm = dm
        self.ai = ai
        self._grading = False
        root = BoxLayout(orientation="vertical")
        root.add_widget(TopBar("AI 批改官", level="CET-4"))

        # mode tabs
        bar = BoxLayout(orientation="horizontal", size_hint_y=None,
                         height=dp(40), padding=[dp(16), 4, dp(16), 4],
                         spacing=dp(8))
        self._btn_essay = Button(
            text="✍️ 写作", font_size=sp(12), bold=True,
            background_color=THEME["primary"], color=[1, 1, 1, 1],
            on_release=lambda *_a: self._set_mode("essay"),
        )
        self._btn_trans = Button(
            text="🗣️ 翻译", font_size=sp(12),
            background_color=THEME["card"], color=THEME["ink"],
            on_release=lambda *_a: self._set_mode("translation"),
        )
        bar.add_widget(self._btn_essay)
        bar.add_widget(self._btn_trans)
        root.add_widget(bar)

        body = BoxLayout(orientation="vertical",
                          padding=[dp(16), dp(8), dp(16), dp(16)],
                          spacing=dp(8))

        # optional topic (for essay)
        self._topic = TextInput(
            hint_text="📌 题目 (写作模式可选)",
            font_size=sp(12), size_hint_y=None, height=dp(36),
            multiline=False, padding=[dp(8), dp(8), dp(8), dp(8)],
        )
        body.add_widget(self._topic)

        # student input — large area, friendly to soft keyboard
        self._student = TextInput(
            hint_text="✍️ 在此输入你的作文 / 翻译...\n建议 80 词以上",
            font_size=sp(13),
            multiline=True,
            padding=[dp(10), dp(10), dp(10), dp(10)],
        )
        body.add_widget(self._student)

        # submit
        body.add_widget(Button(
            text="🤖  提交 AI 精批",
            font_size=sp(14), bold=True,
            background_color=THEME["primary"], color=[1, 1, 1, 1],
            size_hint_y=None, height=dp(44),
            on_release=lambda *_a: self._submit(),
        ))

        # report
        scroll = ScrollView(size_hint_y=0.6)
        self._report = Label(
            text="(批改结果会显示在这里)", font_size=sp(12),
            color=THEME["muted"],
            halign="left", valign="top",
            markup=True,
            size_hint_y=None,
        )
        self._report.bind(size=lambda *_a: setattr(
            self._report, "text_size", self._report.size,
        ))
        # wrap in a sized layout
        report_box = BoxLayout(orientation="vertical", size_hint_y=None,
                                padding=[dp(8), dp(8), dp(8), dp(8)])
        report_box.bind(minimum_height=report_box.setter("height"))
        self._report.bind(texture_size=lambda *_a:
                          setattr(self._report, "height",
                                  self._report.texture_size[1] + dp(8)))
        report_box.add_widget(self._report)
        scroll.add_widget(report_box)
        body.add_widget(scroll)

        root.add_widget(body)
        self.add_widget(root)
        self._mode = "essay"

    def _set_mode(self, mode: str):
        self._mode = mode
        if mode == "essay":
            self._btn_essay.background_color = THEME["primary"]
            self._btn_essay.color = [1, 1, 1, 1]
            self._btn_trans.background_color = THEME["card"]
            self._btn_trans.color = THEME["ink"]
            self._student.hint_text = "✍️ 在此输入你的作文 (建议 80 词以上)"
        else:
            self._btn_trans.background_color = THEME["primary"]
            self._btn_trans.color = [1, 1, 1, 1]
            self._btn_essay.background_color = THEME["card"]
            self._btn_essay.color = THEME["ink"]
            self._student.hint_text = "🗣️ 在此输入你的中文翻译..."

    def _submit(self):
        if self._grading:
            return
        text = self._student.text.strip()
        if len(text) < 20:
            self._report.text = "[color=ff8800]⚠ 输入过短,至少 20 字符[/color]"
            return
        self._grading = True
        self._report.text = "[color=3b82f6]⏳ AI 老师正在批改...[/color]"

        def worker():
            try:
                if self._mode == "essay":
                    r = self.ai.grade_essay(text, topic=self._topic.text,
                                             level="CET4")
                else:
                    # translation: use the text as the english attempt,
                    # no separate Chinese/ref — falls back to local heuristic.
                    r = self.ai.grade_translation_line_by_line(
                        self._topic.text or "(未提供中文原文)",
                        "", text,
                    )
            except Exception as exc:
                r = {"summary": f"AI 调用失败: {exc}"}
            Clock.schedule_once(lambda _dt: self._render(r), 0)

        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _render(self, r: dict):
        self._grading = False
        if not r:
            r = {"summary": "(无报告)"}
        # Build a Kivy-markup string
        out = []
        if "score" in r and isinstance(r["score"], (int, float)):
            score = r["score"]
            color = "10b981" if score >= 12 else "f59e0b" if score >= 8 else "ef4444"
            out.append(f"[b][color={color}][size=20]综合评分: {score} / 15[/size][/color][/b]\n")
        if r.get("summary"):
            out.append(f"[b]📝 总评[/b]\n{r['summary']}\n")
        if r.get("missing_points"):
            out.append("[b]🔴 采分点遗漏[/b]")
            for m in r["missing_points"][:5]:
                out.append(f"  · [color=ef4444]{m}[/color]")
        if r.get("chinglish"):
            out.append("\n[b]⚠️ 中式英语硬伤[/b]")
            for e in r["chinglish"][:5]:
                if isinstance(e, dict):
                    out.append(f"  原句: {e.get('sentence','')}")
                    out.append(f"  问题: [color=ef4444]{e.get('issue','')}[/color]")
                    out.append(f"  建议: [color=10b981]{e.get('fix','')}[/color]")
        if r.get("upgrades"):
            out.append("\n[b]💎 替换建议[/b]")
            for u in r["upgrades"][:5]:
                if isinstance(u, dict):
                    out.append(f"  {u.get('from','')} → [b][color=8b5cf6]{u.get('to','')}[/color][/b]")
        if r.get("polished"):
            out.append(f"\n[b]🌟 润色版[/b]\n[color=10b981]{r['polished']}[/color]")
        self._report.text = "\n".join(out) or "(报告为空)"


# ===========================================================================
# App root
# ===========================================================================
class CETMobileApp(App):
    title = "CET 智胜 · Mobile"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.dm = DataManager(db_path=DB_PATH)
        self.ai = AIService()
        print(f"[mobile_main] DataManager bound to {self.dm.db_path}")

    def build(self):
        # Root: top bar / screen area / bottom nav
        root = BoxLayout(orientation="vertical")

        # Top bar lives in each screen; this is a tiny branding strip
        brand = BoxLayout(orientation="horizontal", size_hint_y=None,
                           height=dp(28), padding=[dp(12), 2, dp(12), 2])
        with brand.canvas.before:
            from kivy.graphics import Color, Rectangle
            Color(0.06, 0.09, 0.16, 1)
            self._brand_bg = Rectangle(pos=brand.pos, size=brand.size)
        brand.bind(pos=self._sync_brand, size=self._sync_brand)
        brand.add_widget(Label(
            text="[ CET 智胜 V2.2 · 移动端 ]",
            color=[1, 1, 1, 1], font_size=sp(10),
            halign="left", valign="middle",
        ))
        brand.add_widget(Label(
            text="[ DB: cet_exam.db ]",
            color=[0.6, 0.85, 1, 1], font_size=sp(9),
            halign="right", valign="middle",
        ))
        root.add_widget(brand)

        # Screen manager
        self.sm = ScreenManager()
        self.sm.size_hint_y = 0.92
        self._screen_dash = DashboardScreen(
            self.dm, on_switch_section=self._switch_to,
            name="dashboard",
        )
        self._screen_vocab = VocabScreen(self.dm, name="vocab")
        self._screen_ai = AIGraderScreen(self.dm, self.ai, name="ai")
        self.sm.add_widget(self._screen_dash)
        self.sm.add_widget(self._screen_vocab)
        self.sm.add_widget(self._screen_ai)
        root.add_widget(self.sm)

        # Bottom nav
        self.nav = BottomNav(on_switch=self._on_nav, size_hint_y=0.08)
        root.add_widget(self.nav)

        return root

    def _sync_brand(self, *_):
        self._brand_bg.pos = self.brand.pos if False else self._brand_pos()
        self._brand_bg.size = self._brand_size()

    def _brand_pos(self):
        return self.root.children[-1].pos  # brand is the topmost child

    def _brand_size(self):
        return self.root.children[-1].size

    def _on_nav(self, key: str):
        self._switch_to(key)

    def _switch_to(self, key: str):
        mapping = {
            "dashboard": "dashboard",
            "vocab": "vocab",
            "ai": "ai",
        }
        target = mapping.get(key, "dashboard")
        self.sm.current = target
        self.nav.set_active(key)


if __name__ == "__main__":
    CETMobileApp().run()
