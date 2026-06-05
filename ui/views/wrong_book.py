"""错题本视图:列出 ``wrong_count > 0`` 的所有单词,按错误次数降序。"""

from __future__ import annotations

import logging
from tkinter import StringVar
from typing import Any

import customtkinter as ctk

from core.data_manager import DataManager
from core.translations import lookup_translation
from ui.fonts import ctk_font
from ui.safe import safe_callback, _logger as _log

_log = logging.getLogger("wrong_book_view")


class WrongBookView(ctk.CTkFrame):
    SECTION_KEY = "wrongbook"
    SECTION_TITLE = "📕  错题本"

    def __init__(self, master, dm: DataManager, level_var: StringVar):
        super().__init__(master, fg_color="transparent")
        self.dm = dm
        self.level_var = level_var
        self._build()
        self.refresh()

    def _build(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(22, 6))
        ctk.CTkLabel(
            header, text="📕  错题本",
            font=ctk_font(size=24, weight="bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            header, text="  ·  答错自动入库,连续 2 次答对自动移出",
            font=ctk_font(size=12),
            text_color=("gray40", "gray60"),
        ).pack(side="left")

        # summary + clear-all button
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=24, pady=(0, 6))
        self.summary_lbl = ctk.CTkLabel(
            top, text="",
            font=ctk_font(size=12),
            text_color=("gray40", "gray60"),
            anchor="w",
        )
        self.summary_lbl.pack(side="left")
        ctk.CTkButton(
            top, text="🔄 刷新", width=70, height=30,
            command=safe_callback(self.refresh),
            font=ctk_font(size=12),
        ).pack(side="right", padx=4)
        ctk.CTkButton(
            top, text="🗑  清空全部错题", width=130, height=30,
            command=safe_callback(self._on_clear_all),
            font=ctk_font(size=12),
            fg_color=("#EF4444", "#B91C1C"),
            hover_color=("#B91C1C", "#EF4444"),
        ).pack(side="right", padx=4)

        # scrollable list
        self.scroll = ctk.CTkScrollableFrame(self, label_text="")
        self.scroll.pack(fill="both", expand=True, padx=24, pady=(6, 22))

    def refresh(self) -> None:
        try:
            for child in self.scroll.winfo_children():
                child.destroy()
            level = self.level_var.get().replace("-", "")
            items = self.dm.list_wrong_book(level)
            n = len(items)
            wrong_total = sum(int(i.get("wrong_count") or 0) for i in items)
            self.summary_lbl.configure(
                text=f"当前 {level}  ·  错题 {n} 词  ·  累计错误 {wrong_total} 次"
            )
            if not items:
                ctk.CTkLabel(
                    self.scroll,
                    text="🎉  错题本空空如也 — 你最近的自测表现很好!",
                    font=ctk_font(size=14),
                    text_color=("#10B981", "#34D399"),
                    pady=20,
                ).pack()
                return
            for i, w in enumerate(items):
                self._build_row(self.scroll, w, i)
        except Exception:
            _log.exception("WrongBookView.refresh failed")
            try:
                ctk.CTkLabel(
                    self.scroll,
                    text="⚠ 加载失败,详情已写入 logs/ui.log",
                    text_color=("#EF4444", "#F87171"), pady=20,
                ).pack()
            except Exception:
                pass

    def _build_row(self, parent, w: dict, index: int) -> None:
        word = w.get("word", "")
        translation = w.get("translation") or ""
        phonetic = w.get("phonetic") or "[/]"
        wrong = int(w.get("wrong_count") or 0)
        consec = int(w.get("consec_correct") or 0)
        # border_color must be a (light, dark) tuple in CTk.
        light_border = "#FCA5A5" if wrong >= 3 else "#E2E8F0"
        dark_border = "#7F1D1D" if wrong >= 3 else "#374151"
        row = ctk.CTkFrame(
            parent, corner_radius=10, border_width=1,
            fg_color=("white", "#1F2937"),
            border_color=(light_border, dark_border),
        )
        row.pack(fill="x", padx=4, pady=6)

        # left: count badge
        badge = ctk.CTkLabel(
            row, text=f"#{index + 1}",
            font=ctk_font(size=12, weight="bold"),
            text_color=("gray40", "gray60"),
            width=40,
        )
        badge.pack(side="left", padx=(10, 4), pady=10)

        # middle: word + translation
        mid = ctk.CTkFrame(row, fg_color="transparent")
        mid.pack(side="left", fill="x", expand=True, padx=8, pady=10)
        line1 = ctk.CTkFrame(mid, fg_color="transparent")
        line1.pack(fill="x", anchor="w")
        ctk.CTkLabel(
            line1, text=word, font=ctk_font(size=18, weight="bold"),
            cursor="hand2", anchor="w",
        ).pack(side="left")
        ctk.CTkLabel(
            line1, text=f"  {phonetic}",
            font=ctk_font(size=12),
            text_color=("gray40", "gray60"),
            anchor="w",
        ).pack(side="left")
        # translation line
        if not translation:
            translation = lookup_translation(word) or "(暂无中文释义)"
        ctk.CTkLabel(
            mid, text=translation, font=ctk_font(size=13),
            text_color=("#1E3A8A", "#93C5FD"),
            wraplength=520, justify="left", anchor="w",
        ).pack(fill="x", anchor="w", pady=(2, 0))
        # example
        ex = w.get("example_sentence") or ""
        if ex:
            ctk.CTkLabel(
                mid, text=f"📌 {ex}",
                font=ctk_font(size=11),
                text_color=("gray20", "gray80"),
                wraplength=520, justify="left", anchor="w",
            ).pack(fill="x", anchor="w", pady=(2, 0))

        # right: error counter + actions
        right = ctk.CTkFrame(row, fg_color="transparent")
        right.pack(side="right", padx=10, pady=10)
        ctk.CTkLabel(
            right, text=f"错 {wrong} 次",
            font=ctk_font(size=14, weight="bold"),
            text_color=("#EF4444", "#F87171"),
        ).pack(anchor="e")
        if consec > 0:
            ctk.CTkLabel(
                right, text=f"已对 {consec}/2",
                font=ctk_font(size=11),
                text_color=("#10B981", "#34D399"),
            ).pack(anchor="e", pady=(2, 0))
        ctk.CTkButton(
            right, text="移除", width=70, height=26,
            command=safe_callback(lambda iid=w["id"]: self._on_remove(iid)),
            font=ctk_font(size=11),
            fg_color=("#E2E8F0", "#2D3748"),
            text_color=("gray10", "gray90"),
            hover_color=("#CBD5E0", "#4A5568"),
        ).pack(anchor="e", pady=(4, 0))

    # ---------- actions ----------
    def _on_remove(self, word_id: int) -> None:
        """Manually remove a word from the wrong book by zeroing its
        wrong_count. Equivalent to a "force-reset"."""
        from tkinter import messagebox
        if not messagebox.askyesno(
            "移出错题本", "确认将该词移出错题本?(wrong_count 清零)",
            parent=self.winfo_toplevel(),
        ):
            return
        try:
            with self.dm._conn() as c:  # type: ignore[attr-defined]
                c.execute(
                    "UPDATE vocabulary "
                    "SET wrong_count = 0, consec_correct = 0 WHERE id = ?",
                    (word_id,),
                )
                c.commit()
            self.refresh()
        except Exception:
            _log.exception("_on_remove failed")
            messagebox.showerror("失败", "移出错题本失败", parent=self)

    def _on_clear_all(self) -> None:
        from tkinter import messagebox
        level = self.level_var.get().replace("-", "")
        if not messagebox.askyesno(
            "清空确认",
            f"确认清空 {level} 的全部错题?(所有 wrong_count 归零)",
            parent=self.winfo_toplevel(),
        ):
            return
        try:
            with self.dm._conn() as c:  # type: ignore[attr-defined]
                c.execute(
                    "UPDATE vocabulary "
                    "SET wrong_count = 0, consec_correct = 0 "
                    "WHERE level = ? AND wrong_count > 0",
                    (level,),
                )
                c.commit()
            self.refresh()
        except Exception:
            _log.exception("_on_clear_all failed")
            messagebox.showerror("失败", "清空失败", parent=self)