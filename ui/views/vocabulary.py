"""Vocabulary view: async DB + lazy/paginated grid rendering.

This file is the rewritten, "silky-smooth" version. The UI is the same
as before; what changed is the I/O model:

* **Async DB.** All sqlite3 calls go through ``core.async_db.AsyncDB``,
  a single background worker thread. The UI thread only ever:
    1. submits a request (gets a ``req_id`` back), and
    2. drains the result queue from ``root.after()``.
  Stale results (the user has changed filters since the query was
  dispatched) are detected by matching ``req_id`` and dropped.

* **Lazy grid.** The first paint of the grid is at most ``PAGE_SIZE``
  cards. As the user scrolls, ``_maybe_load_more`` watches the
  inner ``Canvas``'s ``<Configure>`` event (CTkScrollableFrame
  repaints the canvas whenever the scroll position changes) and
  appends the next page when the bottom is within
  ``LOAD_MORE_THRESHOLD_PX`` pixels of the viewport. No timer loop
  needed — the event drives it.

* **Pagination buttons still work.** Prev/Next/Star filter/Search
  reset the grid to the first page; the existing UI is preserved
  end-to-end.
"""

from __future__ import annotations

import logging
from tkinter import StringVar
from typing import Any

import customtkinter as ctk

from core.async_db import AsyncDB
from core.data_manager import DataManager
from core.translations import lookup_translation
from ui.components import StarRating
from ui.fonts import font as ctk_font
from ui.safe import safe_callback, _logger as _log

_log = logging.getLogger("vocab_view")

PAGE_SIZE = 30            # one logical "page" — kept for back-compat
LAZY_INITIAL = 30         # how many cards to draw on first paint
LAZY_STEP = 30            # how many to add when the user nears the bottom
LOAD_MORE_THRESHOLD_PX = 200  # distance from bottom that triggers next step


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
        # Lazy-rendering state
        self._rendered = 0  # how many cards of the current page are built
        self._inner_canvas: Any = None  # bound after _build() runs
        # Async state
        self._adb = AsyncDB(dm, on_result=safe_callback(self._on_db_result))
        self._latest_req_id: int | None = None
        self._inflight_stats_req: int | None = None
        self._stats_text: str = ""
        self._pending_dist: dict[int, int] = {}
        # Pump the async queue from the Tk main loop. 50ms is well below
        # the 16ms-per-frame budget * 3, so it doesn't add visible latency.
        self.after(50, self._pump_async)

        self._build()

    # ===================================================================
    # LAYOUT (unchanged UI structure)
    # ===================================================================
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

        self._star_btns: list[tuple[Any, ctk.CTkButton]] = []
        all_btn = ctk.CTkButton(
            filters, text="全部", width=58, height=30,
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
                command=safe_callback(lambda s=star: self._on_filter_star(s)),
                fg_color=("#E2E8F0", "#2D3748"),
                text_color=("gray10", "gray90"),
                hover_color=("#2563EB", "#60A5FA"),
                font=ctk_font(size=12, weight="bold"),
            )
            btn.pack(side="left", padx=3)
            self._star_btns.append((star, btn))

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
            self, text="加载中…", font=ctk_font(size=12),
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
        # "Load more" indicator on the right
        self.load_more_lbl = ctk.CTkLabel(
            self.pager_bar, text="", font=ctk_font(size=11),
            text_color=("#10B981", "#34D399"),
        )
        self.load_more_lbl.pack(side="right", padx=8)

        # ---- scrollable grid ----
        self.grid_frame = ctk.CTkScrollableFrame(self, label_text="")
        self.grid_frame.pack(fill="both", expand=True, padx=24, pady=(0, 18))

        # Bind to the inner canvas for lazy load-on-scroll. CTkScrollableFrame
        # exposes ``_parent_canvas`` (the actual Tk Canvas). We attach to its
        # <Configure> event so any scroll-driven reposition triggers a check.
        try:
            self._inner_canvas = self.grid_frame._parent_canvas  # type: ignore[attr-defined]
            self._inner_canvas.bind(
                "<Configure>",
                safe_callback(self._on_canvas_configure),
                add="+",
            )
            # Mouse wheel / scrollbar drags also fire <Button-4/5> or
            # <MouseWheel> on Windows. Bind the latter too so lazy-load
            # works with the scroll wheel, not just window resize.
            self._inner_canvas.bind(
                "<MouseWheel>",
                safe_callback(self._on_mousewheel),
                add="+",
            )
        except Exception:
            _log.exception("could not bind to inner canvas (lazy-load degraded)")

    # ===================================================================
    # ASYNC DB PIPELINE
    # ===================================================================
    def _pump_async(self) -> None:
        """Drain finished DB results on the main thread, then re-arm."""
        try:
            self._adb.pump()
        except Exception:
            _log.exception("_pump_async failed")
        self.after(50, self._pump_async)

    def _on_db_result(self, req_id: int, result: Any) -> None:
        """Called by AsyncDB on the Tk thread. ``result`` is a _Result."""
        method = getattr(result, "method", "")
        if not result.ok:
            _log.error(
                f"async db call {method!r} failed: {result.error}\n{result.error_tb}"
            )
            if method == "list_vocabulary" and req_id == self._latest_req_id:
                self._show_load_error()
            return

        if method == "list_vocabulary":
            if req_id != self._latest_req_id:
                # Stale result — user has changed filters since. Drop.
                _log.debug(f"dropping stale list_vocabulary req_id={req_id}")
                return
            self._all_words = list(result.value or [])
            self._render_stats_sync()
            self._render_page(reset=True)
            # Kick off stats query next (also async)
            self._submit_stats()
            return

        if method == "star_distribution":
            if req_id == self._inflight_stats_req:
                self._apply_stats(result.value or {})
            return

    def _submit_stats(self) -> None:
        try:
            level = self.level_var.get().replace("-", "")
        except Exception:
            level = ""
        self._inflight_stats_req = self._adb.submit("star_distribution", level=level)

    def _show_load_error(self) -> None:
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
        try:
            self.stats_bar.configure(text="⚠ 加载失败")
        except Exception:
            pass

    # ===================================================================
    # REFRESH / STATS / PAGE (now async or async-aware)
    # ===================================================================
    def refresh(self) -> None:
        """Kick off a fresh async fetch. The actual list will arrive via
        _on_db_result a few ms later."""
        try:
            level = self.level_var.get().replace("-", "")
        except Exception:
            level = ""
        # Optimistic UI: clear old grid and show "loading…"
        self._clear_grid()
        try:
            ctk.CTkLabel(
                self.grid_frame, text="⏳ 正在加载…",
                text_color=("gray40", "gray60"), pady=20,
            ).pack()
        except Exception:
            pass
        try:
            self.page_label.configure(text="…")
        except Exception:
            pass
        self._latest_req_id = self._adb.submit(
            "list_vocabulary",
            level=level,
            exact_star=self._exact_star,
            search=self._search_query or None,
        )

    def _render_stats_sync(self) -> None:
        """Render an interim stats line (without distribution, which
        arrives separately)."""
        try:
            level = self.level_var.get().replace("-", "")
        except Exception:
            level = ""
        filter_text = (
            "当前过滤: 全部" if self._exact_star is None
            else f"当前过滤: 严格 {self._exact_star}★"
        )
        self._stats_text = (
            f"{level}  ·  词库共 {sum(self._pending_dist.values()) if self._pending_dist else '?'} 词"
            f"  ·  {filter_text}  ·  显示 {len(self._all_words)} 个"
        )
        try:
            self.stats_bar.configure(text=self._stats_text)
        except Exception:
            pass

    def _apply_stats(self, dist: dict[int, int]) -> None:
        self._pending_dist = dist
        try:
            level = self.level_var.get().replace("-", "")
        except Exception:
            level = ""
        dist_text = "  ".join(f"{s}★×{dist.get(s, 0)}" for s in range(1, 6))
        filter_text = (
            "当前过滤: 全部" if self._exact_star is None
            else f"当前过滤: 严格 {self._exact_star}★"
        )
        try:
            self.stats_bar.configure(
                text=f"{level}  ·  词库共 {sum(dist.values())} 词  ·  "
                     f"{dist_text}  ·  {filter_text}  ·  显示 {len(self._all_words)} 个"
            )
        except Exception:
            pass

    def _render_page(self, reset: bool = False) -> None:
        """First-pass render of the current page. After this, lazy
        loading takes over via _maybe_load_more."""
        if reset:
            self._clear_grid()
        if not self._all_words:
            try:
                ctk.CTkLabel(
                    self.grid_frame, text="(没有匹配的单词,试试调整筛选或搜索条件)",
                    text_color=("gray40", "gray60"), pady=20,
                ).pack()
            except Exception:
                pass
            try:
                self.page_label.configure(text="—")
            except Exception:
                pass
            return

        total_pages = max(1, (len(self._all_words) + PAGE_SIZE - 1) // PAGE_SIZE)
        if self._page >= total_pages:
            self._page = total_pages - 1
        if self._page < 0:
            self._page = 0

        try:
            self.page_label.configure(
                text=f"第 {self._page + 1}/{total_pages} 页"
            )
        except Exception:
            pass

        # Initial chunk
        self._rendered = 0
        self._append_chunk(LAZY_INITIAL)
        self._update_load_more_label()

    def _append_chunk(self, n: int) -> None:
        start = self._page * PAGE_SIZE
        end = start + PAGE_SIZE
        page_words = self._all_words[start:end]
        target = min(self._rendered + n, len(page_words))
        # We need grid_columnconfigure(0..2) set so cards land in 3 cols.
        # Only the parent grid_frame is configured, not its individual cols —
        # call _ensure_grid_cols once before building.
        self._ensure_grid_cols()
        for i in range(self._rendered, target):
            try:
                w = page_words[i]
                self._build_word_card(self.grid_frame, w, i)
            except Exception:
                _log.exception(f"_build_word_card failed for word={w.get('word')!r}")
        self._rendered = target

    def _ensure_grid_cols(self) -> None:
        for col in range(3):
            try:
                self.grid_frame.grid_columnconfigure(col, weight=1, uniform="vocab")
            except Exception:
                pass

    def _clear_grid(self) -> None:
        try:
            for child in self.grid_frame.winfo_children():
                child.destroy()
        except Exception:
            _log.exception("clear grid failed")
        self._rendered = 0

    def _update_load_more_label(self) -> None:
        start = self._page * PAGE_SIZE
        end = start + PAGE_SIZE
        page_words = self._all_words[start:end]
        remaining = len(page_words) - self._rendered
        try:
            if remaining <= 0:
                self.load_more_lbl.configure(text="")
            else:
                self.load_more_lbl.configure(
                    text=f"再滚到底自动加载 {min(remaining, LAZY_STEP)} 个 / 还剩 {remaining}"
                )
        except Exception:
            pass

    # ===================================================================
    # LAZY LOAD TRIGGERS
    # ===================================================================
    def _on_canvas_configure(self, _event: Any = None) -> None:
        """Fires whenever the inner canvas is resized or scrolled.
        Cheap to call — we early-out unless the bottom is close."""
        self._maybe_load_more()

    def _on_mousewheel(self, _event: Any = None) -> None:
        # MouseWheel fires on Windows; let the default handler still
        # run (don't return "break") and just check after.
        self.after(10, self._maybe_load_more)

    def _maybe_load_more(self) -> None:
        if not self._all_words:
            return
        start = self._page * PAGE_SIZE
        end = start + PAGE_SIZE
        page_words = self._all_words[start:end]
        if self._rendered >= len(page_words):
            return
        try:
            canvas = self._inner_canvas
            if canvas is None:
                return
            # canvas.bbox("all") gives the full content bounding box in
            # canvas coords. canvas.canvasy(0) gives the visible window's
            # top in canvas coords. Together they tell us how close we
            # are to the bottom.
            bbox = canvas.bbox("all")
            if not bbox:
                return
            _, y0, _, y1 = bbox
            win_top = canvas.canvasy(0)
            win_h = canvas.winfo_height()
            win_bottom = win_top + win_h
            # Distance from current viewport bottom to content bottom
            gap = y1 - win_bottom
            if gap <= LOAD_MORE_THRESHOLD_PX:
                self._append_chunk(LAZY_STEP)
                self._update_load_more_label()
        except Exception:
            _log.exception("_maybe_load_more failed")

    # ===================================================================
    # CARD DETAIL DIALOG (unchanged behaviour, safe_callback'd)
    # ===================================================================
    def _open_detail(self, index: int) -> None:
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

    # ===================================================================
    # CARD RENDERING (unchanged)
    # ===================================================================
    @staticmethod
    def _display_translation(w: dict) -> tuple[str, bool]:
        """Return (text_to_show, is_fallback)."""
        tr = (w.get("translation") or "").strip()
        if tr:
            return tr, False
        fb = w.get("translation_fallback")
        if fb:
            return fb, True
        fb2 = lookup_translation(w.get("word") or "")
        if fb2:
            return fb2, True
        return "(暂无中文释义)", False

    @staticmethod
    def _display_phonetic(w: dict) -> tuple[str, bool]:
        ph = (w.get("phonetic") or "").strip()
        if ph:
            return ph, False
        return "[/]", True

    def _build_word_card(self, parent, w: dict, index: int) -> None:
        row, col = divmod(index, 3)
        is_mastered = bool(w.get("mastered"))
        light_border = "#10B981" if is_mastered else "#E2E8F0"
        dark_border = "#10B981" if is_mastered else "#374151"
        card = ctk.CTkFrame(
            parent, corner_radius=10, border_width=1,
            fg_color=("white", "#1F2937"),
            border_color=(light_border, dark_border),
        )
        card.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")

        # Click on release (上一轮已修复闪退的关键点)
        try:
            card.bind(
                "<ButtonRelease-1>",
                safe_callback(lambda _e, idx=index: self._open_detail(idx)),
            )
        except Exception:
            pass

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 0))
        word_lbl = ctk.CTkLabel(
            top, text=w.get("word") or "",
            font=ctk_font(size=16, weight="bold"),
            anchor="w", cursor="hand2",
        )
        word_lbl.pack(side="left")
        try:
            word_lbl.bind(
                "<ButtonRelease-1>",
                safe_callback(lambda _e, idx=index: self._open_detail(idx)),
            )
        except Exception:
            pass
        try:
            StarRating(top, stars=int(w.get("star_rating") or 0)).pack(side="right")
        except Exception:
            pass

        phonetic, is_ph_fb = self._display_phonetic(w)
        ctk.CTkLabel(
            card, text=phonetic,
            text_color=("#6B7280", "#9CA3AF") if not is_ph_fb else ("#9CA3AF", "#6B7280"),
            font=ctk_font(size=11),
            anchor="w",
        ).pack(fill="x", padx=12)

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

        bottom = ctk.CTkFrame(card, fg_color="transparent")
        bottom.pack(fill="x", padx=12, pady=(4, 10))
        if is_mastered:
            ctk.CTkLabel(
                bottom, text="✓ 已掌握",
                font=ctk_font(size=10, weight="bold"),
                text_color=("#10B981", "#34D399"),
            ).pack(side="left")
        tag = w.get("tags") or ""
        ctk.CTkLabel(
            bottom, text=f"频次: {w.get('frequency') or 0}   ·   {tag}",
            font=ctk_font(size=10),
            text_color=("#3B82F6", "#60A5FA"), anchor="e",
        ).pack(side="right")

    # ===================================================================
    # HANDLERS
    # ===================================================================
    def _restyle_star_buttons(self, active_star: int | None) -> None:
        try:
            for s, btn in self._star_btns:
                is_active = s == active_star
                btn.configure(
                    fg_color=("#3B82F6" if is_active else ("#E2E8F0", "#2D3748")),
                    text_color=("white" if is_active else ("gray10", "gray90")),
                )
        except Exception:
            _log.exception("star button restyle failed")

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
            self._render_page(reset=True)

    @safe_callback
    def _next_page(self) -> None:
        total_pages = max(1, (len(self._all_words) + PAGE_SIZE - 1) // PAGE_SIZE)
        if self._page + 1 < total_pages:
            self._page += 1
            self._render_page(reset=True)

    def destroy(self) -> None:  # type: ignore[override]
        # Cleanly stop the async worker so the thread doesn't outlive us.
        try:
            self._adb.shutdown(timeout=0.5)
        except Exception:
            pass
        super().destroy()
