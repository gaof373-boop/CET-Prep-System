"""跨板块错词捕捉小工具:让 writing/translation 板块能一键把生词
扔进【词汇 -> 🟥 错题本】。

UI:一个小弹窗(CTkToplevel),内含:
    - 单行输入框:用户输入要捕捉的单词
    - (可选)中文释义输入框
    - [➕ 加入错题本] 按钮
    - [✖ 关闭] 按钮
    - 底部状态条,显示「✓ XXX 已加入错题本(新建行) / wrong_count+1(已存在)」
"""

from __future__ import annotations

import logging
import re
import tkinter as tk
from typing import Callable, Optional

import customtkinter as ctk
from tkinter import messagebox

from core.data_manager import DataManager
from ui.fonts import ctk_font
from ui.safe import safe_callback, _logger as _log

_log = logging.getLogger("catch_dialog")


def _normalize_word(s: str) -> str:
    """Strip non-alphabetic chars from a pasted word; lowercase."""
    return re.sub(r"[^A-Za-z'-]", "", s).strip().lower()


def _normalize_translation(s: str) -> str:
    return s.strip()


class CatchWordDialog(ctk.CTkToplevel):
    """A small dialog that captures ONE word at a time and pushes it
    into the wrong book via :func:`DataManager.add_word_to_wrong_book`.
    """

    def __init__(self, master, dm: DataManager, *,
                 section: str = "writing", level: str = "CET4",
                 prefill_word: str = "", prefill_translation: str = "",
                 on_after_save: Optional[Callable[[], None]] = None,
                 allow_loop: bool = True):
        super().__init__(master)
        self.dm = dm
        self.section = section
        self.level = level
        self.on_after_save = on_after_save
        self.allow_loop = allow_loop
        self.title(f"➕ 捕捉{('写作' if section=='writing' else '翻译')}错词到错题本")
        self.geometry("520x320")
        self.resizable(False, False)
        # Center on parent
        try:
            x = master.winfo_rootx() + 60
            y = master.winfo_rooty() + 80
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass
        # ---- contents ----
        ctk.CTkLabel(
            self, text="🟥  把这次写译暴露的生词加入错题本",
            font=ctk_font(size=15, weight="bold"),
        ).pack(anchor="w", padx=18, pady=(16, 6))
        ctk.CTkLabel(
            self,
            text=f"级别: {level}  ·  板块: {section}",
            font=ctk_font(size=11),
            text_color=("gray40", "gray60"),
        ).pack(anchor="w", padx=18, pady=(0, 8))
        # word row
        ctk.CTkLabel(self, text="英文单词:", font=ctk_font(size=12, weight="bold"),
                     ).grid(row=0, column=0, sticky="w", padx=18, pady=2)
        self.word_var = tk.StringVar(value=prefill_word)
        self.word_entry = ctk.CTkEntry(
            self, textvariable=self.word_var, width=280, height=32,
            placeholder_text="例如: ambiguous / inertia / prosperity",
            font=ctk_font(size=13),
        )
        self.word_entry.grid(row=0, column=1, sticky="we", padx=8, pady=2)
        # translation row
        ctk.CTkLabel(self, text="中文释义(可选):", font=ctk_font(size=12, weight="bold"),
                     ).grid(row=1, column=0, sticky="w", padx=18, pady=2)
        self.trans_var = tk.StringVar(value=prefill_translation)
        self.trans_entry = ctk.CTkEntry(
            self, textvariable=self.trans_var, width=280, height=32,
            placeholder_text="例如: 模糊的 / 惯性 / 繁荣",
            font=ctk_font(size=13),
        )
        self.trans_entry.grid(row=1, column=1, sticky="we", padx=8, pady=2)
        # status
        self.status_lbl = ctk.CTkLabel(
            self, text="",
            font=ctk_font(size=12),
            text_color=("#10B981", "#34D399"),
        )
        self.status_lbl.grid(row=2, column=0, columnspan=2, sticky="we", padx=18, pady=(8, 4))
        # buttons
        ctk.CTkButton(
            self, text="➕  加入错题本", width=160, height=40,
            font=ctk_font(size=14, weight="bold"),
            fg_color=("#EF4444", "#B91C1C"),
            hover_color=("#B91C1C", "#EF4444"),
            command=safe_callback(self._on_save),
        ).grid(row=3, column=0, sticky="w", padx=18, pady=14)
        ctk.CTkButton(
            self, text="✖  关闭", width=100, height=40,
            font=ctk_font(size=13),
            fg_color=("#E2E8F0", "#1F2937"),
            text_color=("gray10", "gray90"),
            hover_color=("#CBD5E0", "#334155"),
            command=safe_callback(self.destroy),
        ).grid(row=3, column=1, sticky="e", padx=18, pady=14)
        self.grid_columnconfigure(1, weight=1)
        # hotkeys
        self.bind("<Return>", safe_callback(lambda _e: self._on_save()))
        self.bind("<Escape>", safe_callback(lambda _e: self.destroy()))
        # initial focus
        try:
            if prefill_word:
                self.trans_entry.focus_set()
            else:
                self.word_entry.focus_set()
        except Exception:
            pass
        # Slightly delayed so the dialog can finish laying out
        try:
            self.after(50, self._focus_first)
        except Exception:
            pass

    def _focus_first(self) -> None:
        try:
            (self.word_entry if not self.word_var.get() else self.trans_entry).focus_set()
        except Exception:
            pass

    def _on_save(self) -> None:
        raw_w = self.word_var.get().strip()
        raw_t = self.trans_var.get().strip()
        if not raw_w:
            self.status_lbl.configure(
                text="⚠ 请先输入英文单词",
                text_color=("#F59E0B", "#FBBF24"),
            )
            try:
                self.word_entry.focus_set()
            except Exception:
                pass
            return
        word = _normalize_word(raw_w)
        if not word:
            self.status_lbl.configure(
                text="⚠ 单词格式无效(只接受字母)",
                text_color=("#F59E0B", "#FBBF24"),
            )
            return
        translation = _normalize_translation(raw_t)
        try:
            row_id, created = self.dm.add_word_to_wrong_book(
                word,
                level=self.level,
                translation=translation,
                source=self.section,
            )
            # 记录到 generated_practice (用作 dashboard 的 AI 助攻计数指标)
            try:
                self.dm.save_ai_catch_log(
                    section=self.section, level=self.level,
                    word=word, source_id=row_id,
                )
            except Exception:
                _log.exception("save_ai_catch_log failed (non-fatal)")
        except Exception as e:
            _log.exception("add_word_to_wrong_book failed")
            self.status_lbl.configure(
                text=f"❌ 保存失败: {e}",
                text_color=("#EF4444", "#F87171"),
            )
            return
        if created:
            self.status_lbl.configure(
                text=f"✅  {word}  新建入错题本 (wrong_count=1)",
                text_color=("#10B981", "#34D399"),
            )
        else:
            self.status_lbl.configure(
                text=f"✅  {word}  已在错题本 (wrong_count+1)",
                text_color=("#10B981", "#34B399" if False else "#10B981"),
            )
        # notify caller so dashboard refreshes
        if self.on_after_save:
            try:
                self.on_after_save()
            except Exception:
                _log.exception("on_after_save callback failed")
        if self.allow_loop:
            # clear inputs and refocus for next word
            self.word_var.set("")
            self.trans_var.set("")
            try:
                self.word_entry.focus_set()
            except Exception:
                pass
        else:
            self.destroy()


def open_catch_dialog(master, dm, *,
                     section: str = "writing", level: str = "CET4",
                     prefill_word: str = "", prefill_translation: str = "",
                     on_after_save: Optional[Callable[[], None]] = None) -> CatchWordDialog:
    """Convenience factory — call this from writing/translation views."""
    dlg = CatchWordDialog(
        master, dm,
        section=section, level=level,
        prefill_word=prefill_word,
        prefill_translation=prefill_translation,
        on_after_save=on_after_save,
    )
    return dlg