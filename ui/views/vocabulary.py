"""Vocabulary view: paginated word grid + 5-star filter + search.

Behaviour:
- 1★/2★/3★/4★/5★ buttons use **strict** filtering: clicking 3★ shows
  *only* 3-star words. An extra "全部" button clears the filter.
- Each card displays the word, phonetic, Chinese translation (with a
  built-in dictionary fallback for words that have empty ``translation``
  in the database), example sentence, and frequency tag.
- Empty phonetic renders as ``[/]`` (placeholder) so layout never breaks.
- Empty translation falls back to the built-in dictionary; if still
  missing, shows "(暂无中文释义)" in italic.
- Pagination: ``PAGE_SIZE = 30`` words per page, prev/next buttons.
"""

from __future__ import annotations

import logging
from tkinter import StringVar
from typing import Any

import customtkinter as ctk

from core.data_manager import DataManager
from core.translations import lookup_translation
from ui.components import StarRating
from ui.fonts import font as ctk_font
from ui.safe import safe_callback, _logger as _log

_log = logging.getLogger("vocab_view")

PAGE_SIZE = 30  # max ~270 widgets per page, well within Tk's safe range


class VocabularyView(ctk.CTkFrame):
    SECTION_KEY = "vocabulary"
    SECTION_TITLE = "📝  词汇板块"

    def __init__(self, master, dm: DataManager, level_var: StringVar):
        super().__init__(master, fg_color="transparent")
        self.dm = dm
        self.level_var = level_var
        self._exact_star: int | None = None  # None = show all stars
        self._search_query = ""
        self._page = 0
        self._all_words: list[dict] = []
        self._build()

    # ---------- layout ----------
    def _build(self) -> None:
        # ---- header ----
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(22, 6))
        ctk.CTkLabel(
            header, text="📝  词汇板块",
            font=ctk_font(size=24, weight="bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            header, text="  ·  按出现频次与重要程度划分星级",
            font=ctk_font(size=12),
            text_color=("gray40", "gray60"),
        ).pack(side="left")

        # ---- filter row: 全部 + 1~5 星 + 搜索 ----
        filters = ctk.CTkFrame(self, fg_color="transparent")
        filters.pack(fill="x", padx=24, pady=(6, 8))
        ctk.CTkLabel(filters, text="星级:", font=ctk_font(size=13)).pack(side="left", padx=(0, 4))

        # "全部" (All) button: clears the star filter
        self._star_btns: list[tuple[Any, ctk.CTkButton]] = []
        all_btn = ctk.CTkButton(
            filters, text="全部", width=58, height=30,
            # IMPORTANT: wrap a lambda (NOT a call!) so the handler is
            # deferred until the user actually clicks the button. If we
            # wrote self._on_filter_all() the body would run during
            # widget construction, before self.stats_bar / self.grid_frame
            # exist, raising AttributeError.
            command=safe_callback(lambda: self._on_filter_all()),
            fg_color=("#3B82F6", "#3B82F6"),
            text_color="white",
            hover_color=("#2563EB", "#60A5FA"),
            font=ctk_font(size=12, weight="bold"),
        )
        all_btn.pack(side="left", padx=3)
        self._star_btns.append((None, all_btn))

        for star in range(1, 6):
            btn = ctk.CTkButton(
                filters, text="★" * star, width=58, height=30,
                # Same pattern: lambda defers the call.
                command=safe_callback(lambda s=star: self._on_filter_star(s)),
                fg_color=("#E2E8F0", "#2D3748"),
                text_color=("gray10", "gray90"),
                hover_color=("#2563EB", "#60A5FA"),
                font=ctk_font(size=12, weight="bold"),
            )
            btn.pack(side="left", padx=3)
            self._star_btns.append((star, btn))

        # Search on the right
        self.search = ctk.CTkEntry(
            filters, placeholder_text="🔍 搜索单词 / 释义…", width=220, height=30,
        )
        self.search.pack(side="right", padx=8)
        self.search.bind("<Return>", safe_callback(lambda _e: self._on_search()))
        ctk.CTkButton(filters, text="搜索", width=58, height=30,
                      command=safe_callback(self._on_search),
                      font=ctk_font(size=12)).pack(side="right")
        ctk.CTkButton(filters, text="重置", width=58, height=30,
                      command=safe_callback(self._on_reset),
                      fg_color=("#E2E8F0", "#2D3748"),
                      text_color=("gray10", "gray90"),
                      hover_color=("#CBD5E0", "#4A5568"),
                      font=ctk_font(size=12)).pack(side="right", padx=4)

        # ---- stats + pagination bar ----
        self.stats_bar = ctk.CTkLabel(
            self, text="", font=ctk_font(size=12),
            text_color=("gray40", "gray60"),
        )
        self.stats_bar.pack(anchor="w", padx=28, pady=(0, 4))

        self.pager_bar = ctk.CTkFrame(self, fg_color="transparent")
        self.pager_bar.pack(fill="x", padx=24, pady=(0, 6))
        ctk.CTkButton(self.pager_bar, text="◀ 上一页", width=90, height=28,
                      command=safe_callback(self._prev_page),
                      font=ctk_font(size=12)).pack(side="left", padx=2)
        ctk.CTkButton(self.pager_bar, text="下一页 ▶", width=90, height=28,
                      command=safe_callback(self._next_page),
                      font=ctk_font(size=12)).pack(side="left", padx=2)
        self.page_label = ctk.CTkLabel(
            self.pager_bar, text="—", font=ctk_font(size=12),
            text_color=("gray40", "gray60"),
        )
        self.page_label.pack(side="left", padx=8)

        # ---- scrollable grid ----
        self.grid_frame = ctk.CTkScrollableFrame(self, label_text="")
        self.grid_frame.pack(fill="both", expand=True, padx=24, pady=(0, 18))

    # ---------- data ----------
    def _load_words(self) -> list[dict]:
        try:
            level = self.level_var.get().replace("-", "")
            return self.dm.list_vocabulary(
                level,
                exact_star=self._exact_star,
                search=self._search_query or None,
            )
        except Exception:
            _log.exception("list_vocabulary failed")
            return []

    # ---------- render ----------
    def refresh(self) -> None:
        try:
            self._all_words = self._load_words()
            self._render_stats()
            self._render_page()
        except Exception:
            _log.exception("VocabularyView.refresh failed")
            try:
                for child in self.grid_frame.winfo_children():
                    child.destroy()
                ctk.CTkLabel(
                    self.grid_frame,
                    text="⚠ 加载失败,详情已写入 logs/ui.log",
                    text_color=("#EF4444", "#F87171"), pady=20,
                ).pack()
            except Exception:
                pass

    # ---------- card click → detail dialog ----------
    def _open_detail(self, index: int) -> None:
        """Pop up the detail dialog for the word at ``index`` in
        the current page."""
        if not self._all_words:
            return
        start = self._page * PAGE_SIZE
        words_on_page = self._all_words[start: start + PAGE_SIZE]
        if not (0 <= index < len(words_on_page)):
            return
        try:
            from ui.views.word_detail import WordDetailDialog
            WordDetailDialog(
                master=self.winfo_toplevel(),
                words=words_on_page,
                start_index=index,
                dm=self.dm,
                on_change=safe_callback(self.refresh),
            )
        except Exception:
            _log.exception("WordDetailDialog failed to open")

    def _render_stats(self) -> None:
        try:
            level = self.level_var.get().replace("-", "")
            dist = self.dm.star_distribution(level)
            total = sum(dist.values())
            dist_text = "  ".join(f"{s}★×{dist.get(s, 0)}" for s in range(1, 6))
            filter_text = (
                f"当前过滤: 全部" if self._exact_star is None
                else f"当前过滤: 严格 {self._exact_star}★"
            )
            self.stats_bar.configure(
                text=f"{level}  ·  词库共 {total} 词  ·  {dist_text}  ·  {filter_text}  ·  显示 {len(self._all_words)} 个"
            )
        except Exception:
            _log.exception("_render_stats failed")

    def _render_page(self) -> None:
        try:
            for child in self.grid_frame.winfo_children():
                child.destroy()
        except Exception:
            _log.exception("clear grid failed")
            return

        if not self._all_words:
            try:
                ctk.CTkLabel(
                    self.grid_frame, text="(没有匹配的单词,试试调整筛选或搜索条件)",
                    text_color=("gray40", "gray60"), pady=20,
                ).pack()
            except Exception:
                pass
            self.page_label.configure(text="—")
            return

        total_pages = max(1, (len(self._all_words) + PAGE_SIZE - 1) // PAGE_SIZE)
        if self._page >= total_pages:
            self._page = total_pages - 1
        if self._page < 0:
            self._page = 0

        start = self._page * PAGE_SIZE
        end = start + PAGE_SIZE
        page_words = self._all_words[start:end]

        for i, w in enumerate(page_words):
            try:
                self._build_word_card(self.grid_frame, w, i)
            except Exception:
                _log.exception(f"_build_word_card failed for word={w.get('word')!r}")

        try:
            self.page_label.configure(
                text=f"第 {self._page + 1}/{total_pages} 页  ·  本页 {len(page_words)} 词"
            )
        except Exception:
            pass

    # ---------- card ----------
    @staticmethod
    def _display_translation(w: dict) -> tuple[str, bool]:
        """Return (text_to_show, is_fallback)."""
        tr = (w.get("translation") or "").strip()
        if tr:
            return tr, False
        # Use the in-memory fallback injected by data_manager
        fb = w.get("translation_fallback")
        if fb:
            return fb, True
        # Last-ditch: try the dict directly
        fb2 = lookup_translation(w.get("word") or "")
        if fb2:
            return fb2, True
        return "(暂无中文释义)", False

    @staticmethod
    def _display_phonetic(w: dict) -> tuple[str, bool]:
        ph = (w.get("phonetic") or "").strip()
        if ph:
            return ph, False
        return "[/]", True  # placeholder; treat as fallback for colour

    def _build_word_card(self, parent, w: dict, index: int) -> None:
        row, col = divmod(index, 3)
        # Card background — explicit high contrast for both modes
        # Mark "mastered" cards with a green left border to make them
        # scannable at a glance.
        is_mastered = bool(w.get("mastered"))
        # CTkFrame.border_color must be a (light, dark) tuple. Always
        # provide both even when only one mode changes.
        light_border = "#10B981" if is_mastered else "#E2E8F0"
        dark_border = "#10B981" if is_mastered else "#374151"
        card = ctk.CTkFrame(
            parent, corner_radius=10, border_width=1,
            fg_color=("white", "#1F2937"),
            border_color=(light_border, dark_border),
        )
        card.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")
        try:
            parent.grid_columnconfigure(col, weight=1, uniform="vocab")
        except Exception:
            pass

        # Make the card clickable: bind a single-click anywhere on the
        # card frame to open the detail dialog. We use a wrapper so
        # exceptions don't crash the main loop.
        try:
            card.bind(
                "<Button-1>",
                safe_callback(lambda _e, idx=index: self._open_detail(idx)),
            )
        except Exception:
            pass

        # Top row: word + stars
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 0))
        word_lbl = ctk.CTkLabel(
            top, text=w.get("word") or "",
            font=ctk_font(size=16, weight="bold"),
            anchor="w", cursor="hand2",
        )
        word_lbl.pack(side="left")
        # Click on the word label also opens detail
        try:
            word_lbl.bind(
                "<Button-1>",
                safe_callback(lambda _e, idx=index: self._open_detail(idx)),
            )
        except Exception:
            pass
        # Star rating
        try:
            StarRating(top, stars=int(w.get("star_rating") or 0)).pack(side="right")
        except Exception:
            pass

        # Phonetic line — always shows, with [/] placeholder if empty
        phonetic, is_ph_fb = self._display_phonetic(w)
        ctk.CTkLabel(
            card, text=phonetic,
            text_color=("#6B7280", "#9CA3AF") if not is_ph_fb else ("#9CA3AF", "#6B7280"),
            font=ctk_font(size=11),
            anchor="w",
        ).pack(fill="x", padx=12)

        # Chinese translation line — always shows, fallback in italic gray
        translation, is_tr_fb = self._display_translation(w)
        ctk.CTkLabel(
            card, text=translation,
            text_color=("#1E3A8A", "#93C5FD") if not is_tr_fb else ("#6B7280", "#9CA3AF"),
            font=ctk_font(
                size=13 if not is_tr_fb else 12,
                weight="bold" if not is_tr_fb else "normal",
            ),
            wraplength=260, justify="left", anchor="w",
        ).pack(fill="x", padx=12, pady=(2, 4))

        # Optional example sentence
        example = w.get("example_sentence") or ""
        if example:
            ctk.CTkLabel(
                card, text=f"📌 {example}",
                wraplength=260, justify="left", anchor="w",
                font=ctk_font(size=11),
                text_color=("gray20", "gray80"),
            ).pack(fill="x", padx=12, pady=(2, 2))
            et = w.get("example_translation") or ""
            if et:
                ctk.CTkLabel(
                    card, text=f"   {et}",
                    wraplength=260, justify="left", anchor="w",
                    font=ctk_font(size=10),
                    text_color=("gray40", "gray60"),
                ).pack(fill="x", padx=12)

        # Bottom: mastered indicator + tag
        bottom = ctk.CTkFrame(card, fg_color="transparent")
        bottom.pack(fill="x", padx=12, pady=(4, 10))
        if is_mastered:
            ctk.CTkLabel(
                bottom, text="✓ 已掌握",
                font=ctk_font(size=10, weight="bold"),
                text_color=("#10B981", "#34D399"),
            ).pack(side="left")
        # Right-aligned tag/freq
        tag = w.get("tags") or ""
        ctk.CTkLabel(
            bottom, text=f"频次: {w.get('frequency') or 0}   ·   {tag}",
            font=ctk_font(size=10),
            text_color=("#3B82F6", "#60A5FA"), anchor="e",
        ).pack(side="right")

    # ---------- handlers ----------
    def _restyle_star_buttons(self, active_star: int | None) -> None:
        """Highlight the active star button (or "All" when None)."""
        try:
            for s, btn in self._star_btns:
                is_active = s == active_star
                btn.configure(
                    fg_color=("#3B82F6" if is_active else ("#E2E8F0", "#2D3748")),
                    text_color=("white" if is_active else ("gray10", "gray90")),
                )
        except Exception:
            _log.exception("star button restyle failed")

    def _make_star_handler(self, star: int):
        def handler():
            self._on_filter_star(star)
        return handler

    @safe_callback
    def _on_filter_star(self, star: int) -> None:
        self._exact_star = star
        self._page = 0
        self._restyle_star_buttons(star)
        self.refresh()

    @safe_callback
    def _on_filter_all(self) -> None:
        self._exact_star = None
        self._page = 0
        self._restyle_star_buttons(None)
        self.refresh()

    @safe_callback
    def _on_search(self) -> None:
        try:
            self._search_query = self.search.get().strip()
        except Exception:
            self._search_query = ""
        self._page = 0
        self.refresh()

    @safe_callback
    def _on_reset(self) -> None:
        self._exact_star = None
        self._search_query = ""
        self._page = 0
        try:
            self.search.delete(0, "end")
        except Exception:
            pass
        self._restyle_star_buttons(None)
        self.refresh()

    @safe_callback
    def _prev_page(self) -> None:
        if self._page > 0:
            self._page -= 1
            self._render_page()

    @safe_callback
    def _next_page(self) -> None:
        total_pages = max(1, (len(self._all_words) + PAGE_SIZE - 1) // PAGE_SIZE)
        if self._page + 1 < total_pages:
            self._page += 1
            self._render_page()
