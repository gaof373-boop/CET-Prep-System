"""📊 V2.0 学霸备考数据看板 — 启动首页。

4 个大数字卡片 + 1 句鼓励性标语 + 跨级别切换。
"""

from __future__ import annotations

import logging
import random
from tkinter import StringVar
from typing import Any

import customtkinter as ctk

from core.data_manager import DataManager
from ui.fonts import ctk_font
from ui.safe import safe_callback, _logger as _log

_log = logging.getLogger("dashboard_view")


QUOTES = [
    "今天也是充满斗志的一天!你已累计在系统内斩落 {n} 个核心考点。",
    "水滴石穿,绳锯木断。再小的进步,都是通往 600+ 路上的真金白银。",
    "英语学习没有速成,只有每天 30 分钟的坚持 — 你的词汇库正在悄悄长大。",
    "不怕慢,只怕站。今天你比昨天多记 5 个词,12 月考场你就会多 5 分底气。",
    "CET 不是天赋的较量,是习惯的较量 — 系统陪你把习惯刻进日历。",
    "真题不是用来背的,是用来悟的。每一道错题都在告诉你:这里还能再稳一点。",
    "你不需要完美,你只需要今天比昨天多坚持 10 分钟。",
    "错题本不是伤疤,是勋章 — 每一道你不再错的题,都是勋章上的一颗星。",
]


class StatCard(ctk.CTkFrame):
    """One of the 4 big-number cards on the dashboard."""

    def __init__(self, master, *, label: str, accent: str, hint: str = ""):
        super().__init__(master, corner_radius=14,
                         fg_color=("white", "#1F2937"),
                         border_width=1,
                         border_color=(accent, accent))
        self.accent = accent
        # big number
        self.num_lbl = ctk.CTkLabel(
            self, text="—",
            font=ctk_font(size=40, weight="bold"),
            text_color=(accent, accent),
        )
        self.num_lbl.pack(padx=20, pady=(20, 0))
        # label
        ctk.CTkLabel(
            self, text=label,
            font=ctk_font(size=13, weight="bold"),
            text_color=("gray10", "gray90"),
        ).pack(padx=20, pady=(0, 4))
        # optional hint
        if hint:
            ctk.CTkLabel(
                self, text=hint,
                font=ctk_font(size=11),
                text_color=("gray40", "gray60"),
            ).pack(padx=20, pady=(0, 16))
        else:
            ctk.CTkLabel(
                self, text=" ", font=ctk_font(size=11),
            ).pack(padx=20, pady=(0, 16))

    def set_value(self, n: int) -> None:
        self.num_lbl.configure(text=f"{n:,}")


class DashboardView(ctk.CTkFrame):
    SECTION_KEY = "dashboard"
    SECTION_TITLE = "📊  学霸看板"

    def __init__(self, master, dm: DataManager, level_var: StringVar):
        super().__init__(master, fg_color="transparent")
        self.dm = dm
        self.level_var = level_var
        self._build()
        self.refresh()

    # =====================================================================
    # Layout
    # =====================================================================
    def _build(self) -> None:
        # ----- header / quote -----
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(28, 4))
        ctk.CTkLabel(
            header, text="📊  学霸备考数据看板",
            font=ctk_font(size=28, weight="bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            header, text="  ·  你的今日战况",
            font=ctk_font(size=13),
            text_color=("gray40", "gray60"),
        ).pack(side="left", padx=8)
        # refresh button
        ctk.CTkButton(
            header, text="🔄  刷新数据", width=110, height=34,
            font=ctk_font(size=12),
            command=safe_callback(self.refresh),
            fg_color=("#E2E8F0", "#1F2937"),
            text_color=("gray10", "gray90"),
            hover_color=("#CBD5E0", "#334155"),
        ).pack(side="right", padx=4)

        # ----- the quote (motto) -----
        self.quote_lbl = ctk.CTkLabel(
            self, text="",
            font=ctk_font(size=14, weight="bold"),
            text_color=("#3B82F6", "#60A5FA"),
            wraplength=1100, justify="center",
        )
        self.quote_lbl.pack(fill="x", padx=24, pady=(8, 16))

        # ----- 4 big cards in a 2x2 grid -----
        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=24, pady=(0, 16))
        grid.grid_columnconfigure(0, weight=1, uniform="dash")
        grid.grid_columnconfigure(1, weight=1, uniform="dash")
        grid.grid_rowconfigure(0, weight=1, uniform="dash")
        grid.grid_rowconfigure(1, weight=1, uniform="dash")

        self.card_mastered = StatCard(
            grid, label="🎯  已掌握词汇",
            accent="#10B981",
            hint="点击单词卡片可标记 ✓ 已掌握",
        )
        self.card_mastered.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        self.card_wrong = StatCard(
            grid, label="🟥  错题攻坚",
            accent="#EF4444",
            hint="在「错题本」板块反复巩固",
        )
        self.card_wrong.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)

        self.card_practice = StatCard(
            grid, label="📚  刷题成就",
            accent="#3B82F6",
            hint="阅读 + 听力总题数",
        )
        self.card_practice.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)

        self.card_ai = StatCard(
            grid, label="🤖  AI 助攻频次",
            accent="#8B5CF6",
            hint="写作批改 + 翻译精批累计",
        )
        self.card_ai.grid(row=1, column=1, sticky="nsew", padx=8, pady=8)

        # ----- bottom hint / quick links -----
        ctk.CTkLabel(
            self, text="💡  在左侧选择具体板块开始练习,或在「错题本」巩固你的薄弱点。",
            font=ctk_font(size=12),
            text_color=("gray40", "gray60"),
        ).pack(padx=24, pady=(0, 18))

    # =====================================================================
    # Refresh
    # =====================================================================
    def refresh(self) -> None:
        try:
            level = self.level_var.get().replace("-", "")
            stats = self.dm.dashboard_stats(level=level)
            self.card_mastered.set_value(stats["mastered"])
            self.card_wrong.set_value(stats["wrong_book"])
            self.card_practice.set_value(
                stats["practice_reading"] + stats["practice_listening"]
            )
            self.card_ai.set_value(
                stats["ai_essay_grades"] + stats["ai_trans_grades"]
            )
            # 1) refresh the count
            n_words = stats["total_words"]
            # 2) 鼓励性标语:动态插值
            tmpl = random.choice(QUOTES)
            try:
                self.quote_lbl.configure(text=tmpl.format(n=n_words))
            except (KeyError, IndexError):
                self.quote_lbl.configure(text=tmpl)
        except Exception:
            _log.exception("DashboardView.refresh failed")
            self.quote_lbl.configure(text="(看板加载失败,详情见 logs/ui.log)")