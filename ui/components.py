"""Reusable CustomTkinter widgets for the CET prep system.

The widgets in this module are tuned for a **clearly labelled, Chinese-
first** sidebar:
- :class:`LevelZoneButton` — the two big "CET-4 四级专区" / "CET-6 六级专区"
  buttons at the top of the sidebar.
- :class:`SectionButton` — the five "📝 词汇板块" / "✍️ 写作板块" / … buttons.
  Inactive state has a solid light/dark surface and a 1-px border; the
  active state is the brand accent colour with white text.
"""

from __future__ import annotations

import customtkinter as ctk
from tkinter import messagebox
from typing import Callable, Iterable

from core.theme_manager import LEVEL_COLORS, SECTION_ICONS
from ui.fonts import ctk_font


# ---------------------------------------------------------------------------
# Section / level switcher (sidebar)
# ---------------------------------------------------------------------------
class SectionButton(ctk.CTkButton):
    """Sidebar button representing one of the 5 sub-sections.

    The label passed in should already include the icon and "板块"
    suffix, e.g. ``"📝 词汇板块"``. This class only handles visual
    state and click styling.
    """

    def __init__(self, master, label: str, command: Callable, **kwargs):
        super().__init__(
            master,
            text=label,
            command=command,
            height=46,
            corner_radius=10,
            # Default (inactive) state — solid surface + 1-px border so
            # the button is never invisible against the sidebar bg.
            fg_color=("#FFFFFF", "#1E293B"),
            text_color=("#0F172A", "#F1F5F9"),
            hover_color=("#E2E8F0", "#334155"),
            border_width=1,
            border_color=("#CBD5E1", "#475569"),
            anchor="w",
            font=ctk_font(size=15, weight="bold"),
            **kwargs,
        )
        self._active = False

    def set_active(self, active: bool, accent: str) -> None:
        if active:
            self.configure(
                fg_color=(accent, accent),
                text_color="white",
                border_color=(accent, accent),
            )
        else:
            self.configure(
                fg_color=("#FFFFFF", "#1E293B"),
                text_color=("#0F172A", "#F1F5F9"),
                border_color=("#CBD5E1", "#475569"),
            )
        self._active = active


class LevelZoneButton(ctk.CTkButton):
    """One of the two big "CET-4 / CET-6" buttons at the top of the sidebar.

    Inactive: white/dark surface + thick border in the brand accent.
    Active: solid accent fill + white text.
    """

    def __init__(self, master, label: str, sub_label: str,
                 command: Callable, accent: str, **kwargs):
        self._accent = accent
        # The visible text combines the big label and a sub-line.
        # We use a 2-line compound text — single font, semicolon separator.
        compound = f"{label}\n{sub_label}"
        super().__init__(
            master,
            text=compound,
            command=command,
            height=62,
            corner_radius=10,
            fg_color=("#FFFFFF", "#1E293B"),
            text_color=("#0F172A", "#F1F5F9"),
            hover_color=("#E2E8F0", "#334155"),
            border_width=2,
            border_color=accent,
            anchor="w",
            # Smaller font so the long Chinese label fits inside a
            # ~200 px sidebar without truncation.
            font=ctk_font(size=13, weight="bold"),
            **kwargs,
        )
        self._active = False

    def set_active(self, active: bool) -> None:
        accent = self._accent
        if active:
            self.configure(
                fg_color=(accent, accent),
                text_color="white",
                border_color=(accent, accent),
            )
        else:
            self.configure(
                fg_color=("#FFFFFF", "#1E293B"),
                text_color=("#0F172A", "#F1F5F9"),
                border_color=accent,
            )
        self._active = active


# ---------------------------------------------------------------------------
# Star rating label
# ---------------------------------------------------------------------------
class StarRating(ctk.CTkLabel):
    """Display '★★★★☆' style rating for vocabulary words."""

    def __init__(self, master, stars: int = 0, **kwargs):
        text = "★" * stars + "☆" * (5 - stars)
        super().__init__(
            master, text=text,
            font=ctk_font(size=14, weight="bold"),
            text_color=("#F59E0B", "#FBBF24"),
            width=80,
            **kwargs,
        )


# ---------------------------------------------------------------------------
# Card frame with title
# ---------------------------------------------------------------------------
class Card(ctk.CTkFrame):
    """A rounded card with optional title and body."""

    def __init__(self, master, title: str | None = None, accent: str | None = None, **kwargs):
        super().__init__(master, corner_radius=12, border_width=1, **kwargs)
        if title:
            header = ctk.CTkFrame(self, fg_color="transparent")
            header.pack(fill="x", padx=14, pady=(12, 0))
            accent_bar = ctk.CTkFrame(header, width=4, height=20, fg_color=accent or "#3B82F6")
            accent_bar.pack(side="left", padx=(0, 8), pady=2)
            ctk.CTkLabel(
                header, text=title, anchor="w",
                font=ctk_font(size=15, weight="bold"),
            ).pack(side="left")
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=14, pady=12)


# ---------------------------------------------------------------------------
# Sidebar logo + tagline
# ---------------------------------------------------------------------------
class AppBrand(ctk.CTkFrame):
    def __init__(self, master, on_toggle_theme: Callable):
        super().__init__(master, fg_color="transparent")
        ctk.CTkLabel(
            self, text="CET 智胜",
            font=ctk_font(size=20, weight="bold"),
        ).pack(anchor="w", padx=18, pady=(18, 0))
        ctk.CTkLabel(
            self, text="英语四六级备考系统",
            font=ctk_font(size=12),
            text_color=("gray40", "gray60"),
        ).pack(anchor="w", padx=18, pady=(0, 12))
        ctk.CTkButton(
            self, text="🌗 切换主题", height=30, corner_radius=8,
            command=on_toggle_theme,
            fg_color=("#E2E8F0", "#1E293B"),
            text_color=("#0F172A", "#F1F5F9"),
            hover_color=("#CBD5E0", "#334155"),
            border_width=1,
            border_color=("#CBD5E1", "#475569"),
        ).pack(fill="x", padx=18, pady=(0, 14))


# ---------------------------------------------------------------------------
# Empty state / info helpers
# ---------------------------------------------------------------------------
def info(master, title: str, message: str) -> None:
    messagebox.showinfo(title, message, parent=master)


def ask_yes_no(master, title: str, message: str) -> bool:
    return messagebox.askyesno(title, message, parent=master)
