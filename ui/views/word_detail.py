"""Word detail dialog: large card with prev/next + mastered checkbox.

Used by the vocabulary view. Click any word card to pop this up.
The dialog is a ``CTkToplevel`` and listens for Left/Right arrow keys
to page through neighbouring words. Closing it returns the user's
attention to the main grid below.
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

import customtkinter as ctk
from tkinter import messagebox

from core.translations import lookup_translation
from ui.fonts import ctk_font
from ui.safe import safe_callback


def _safe_translation(word: str, db_value: str) -> str:
    """DB value (may be empty) → local dictionary fallback → "(暂无)".
    The vocabulary view's list_vocabulary already injects
    translation_fallback, but for the detail dialog we duplicate
    the logic to stay self-contained.
    """
    if db_value and db_value.strip():
        return db_value.strip()
    fb = lookup_translation(word)
    return fb if fb else ""


class WordDetailDialog:
    """Modal-ish detail dialog. NOT grab_set() so the user can still
    click on the underlying grid if they want to compare words."""

    def __init__(
        self,
        master: ctk.CTk,
        words: Sequence[dict[str, Any]],
        start_index: int,
        dm,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        """
        Args:
            master: parent window.
            words: list of vocabulary row dicts (the page that's visible).
            start_index: which entry in ``words`` to show first.
            dm: DataManager (for mastered toggle + neighbour fetch).
            on_change: optional callback invoked when mastered state flips.
        """
        self.master = master
        self.words = list(words)
        self.dm = dm
        self.on_change = on_change
        self._index = max(0, min(start_index, len(self.words) - 1))

        self.win = ctk.CTkToplevel(master)
        self.win.title("🔎  单词详情")
        self.win.geometry("820x560")
        # Do NOT call grab_set() — we want the underlying grid clickable.
        # Center on the parent.
        self.win.update_idletasks()
        try:
            x = master.winfo_rootx() + 80
            y = master.winfo_rooty() + 60
            self.win.geometry(f"+{x}+{y}")
        except Exception:
            pass

        # ----- top: word + phonetic + pos -----
        top = ctk.CTkFrame(self.win, fg_color="transparent")
        top.pack(fill="x", padx=22, pady=(18, 8))
        self.word_lbl = ctk.CTkLabel(
            top, text="", font=ctk_font(size=32, weight="bold"),
        )
        self.word_lbl.pack(side="left")
        self.phon_lbl = ctk.CTkLabel(
            top, text="", font=ctk_font(size=16),
            text_color=("gray40", "gray60"),
        )
        self.phon_lbl.pack(side="left", padx=12)

        # ----- middle: translation + tags -----
        self.trans_lbl = ctk.CTkLabel(
            self.win, text="", font=ctk_font(size=18, weight="bold"),
            text_color=("#3B82F6", "#60A5FA"),
            anchor="w", wraplength=760, justify="left",
        )
        self.trans_lbl.pack(fill="x", padx=22, pady=(2, 12))
        self.meta_lbl = ctk.CTkLabel(
            self.win, text="", font=ctk_font(size=12),
            text_color=("gray40", "gray60"),
            anchor="w",
        )
        self.meta_lbl.pack(fill="x", padx=22, pady=(0, 8))

        # ----- example sentence block -----
        ex_label = ctk.CTkLabel(
            self.win, text="📝  例句",
            font=ctk_font(size=14, weight="bold"), anchor="w",
        )
        ex_label.pack(fill="x", padx=22, pady=(8, 4))
        self.ex_en = ctk.CTkTextbox(self.win, height=80, wrap="word",
                                    font=ctk_font(size=13))
        self.ex_en.pack(fill="x", padx=22, pady=2)
        self.ex_zh = ctk.CTkLabel(
            self.win, text="", font=ctk_font(size=12),
            text_color=("gray20", "gray80"),
            wraplength=760, justify="left", anchor="w",
        )
        self.ex_zh.pack(fill="x", padx=22, pady=(2, 12))

        # ----- bottom: mastered checkbox + nav buttons -----
        bottom = ctk.CTkFrame(self.win, fg_color="transparent")
        bottom.pack(fill="x", padx=22, pady=(4, 18), side="bottom")
        self.mastered_var = ctk.BooleanVar(value=False)
        self.mastered_chk = ctk.CTkCheckBox(
            bottom, text="✓  已掌握 (下次自测的题库来源)",
            variable=self.mastered_var,
            command=safe_callback(self._on_toggle_mastered),
            font=ctk_font(size=13, weight="bold"),
        )
        self.mastered_chk.pack(side="left", padx=4)

        ctk.CTkButton(
            bottom, text="⬅ 上一个", width=110, height=36,
            command=safe_callback(self._prev),
            font=ctk_font(size=13, weight="bold"),
        ).pack(side="right", padx=4)
        ctk.CTkButton(
            bottom, text="下一个 ➡", width=110, height=36,
            command=safe_callback(self._next),
            font=ctk_font(size=13, weight="bold"),
        ).pack(side="right", padx=4)

        # keyboard bindings
        self.win.bind("<Left>", safe_callback(lambda _e: self._prev()))
        self.win.bind("<Right>", safe_callback(lambda _e: self._next()))
        self.win.bind("<Escape>", safe_callback(lambda _e: self.win.destroy()))
        # Also bind the focus to make arrow keys work even if a button has focus
        self.win.bind("<Key>", safe_callback(self._on_key))

        self._render()

    # ---------- handlers ----------
    def _on_key(self, event) -> None:
        # Some CTk buttons consume arrow events when focused; fall back
        # to a global handler so left/right always works.
        ks = getattr(event, "keysym", "")
        if ks == "Left":
            self._prev()
        elif ks == "Right":
            self._next()

    def _prev(self) -> None:
        if self._index > 0:
            self._index -= 1
            self._render()

    def _next(self) -> None:
        if self._index < len(self.words) - 1:
            self._index += 1
            self._render()

    def _on_toggle_mastered(self) -> None:
        w = self._current_word()
        if not w:
            return
        new_state = self.mastered_var.get()
        try:
            self.dm.set_mastered(w["id"], new_state)
        except Exception as e:
            messagebox.showerror("保存失败", str(e), parent=self.win)
            self.mastered_var.set(not new_state)
            return
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                pass

    # ---------- render ----------
    def _current_word(self) -> dict[str, Any] | None:
        if not self.words:
            return None
        if not (0 <= self._index < len(self.words)):
            return None
        return self.words[self._index]

    def _render(self) -> None:
        w = self._current_word()
        if not w:
            self.word_lbl.configure(text="(无内容)")
            return
        word = w.get("word", "")
        phonetic = w.get("phonetic") or ""
        translation = _safe_translation(word, w.get("translation", ""))
        pos = w.get("pos") or ""
        freq = w.get("frequency") or 0
        stars = w.get("star_rating") or 0
        example_en = w.get("example_sentence") or ""
        example_zh = w.get("example_translation") or ""
        mastered = bool(w.get("mastered"))
        wrong_count = w.get("wrong_count") or 0

        # Title: "word  (5/30)"
        self.word_lbl.configure(text=f"{word}  ")
        self.phon_lbl.configure(text=phonetic if phonetic else "[/]")
        # translation
        self.trans_lbl.configure(
            text=f"{pos}  {translation}" if pos else (translation or "(暂无中文释义)")
        )
        # meta
        meta_bits = [
            f"⭐ {stars}/5",
            f"频次: {freq}",
            f"错题: {wrong_count} 次" if wrong_count else None,
        ]
        self.meta_lbl.configure(text="  ·  ".join(b for b in meta_bits if b))
        # examples
        self.ex_en.configure(state="normal")
        self.ex_en.delete("1.0", "end")
        self.ex_en.insert("1.0", example_en or "(暂无例句)")
        self.ex_en.configure(state="disabled")
        self.ex_zh.configure(text=example_zh)
        # mastered checkbox
        self.mastered_var.set(mastered)
        # window title
        self.win.title(
            f"🔎  {word}  ({self._index + 1}/{len(self.words)})"
        )