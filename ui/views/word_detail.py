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
        # Bind to parent so WM treats this as a child window (no separate
        # taskbar icon, no focus stealing surprises on Win32).
        try:
            self.win.transient(master)
        except Exception:
            pass
        # Make the close button call destroy() explicitly, so we never
        # depend on Tk's default WM_DELETE_WINDOW path — that path is
        # the most common source of "flash-and-close" on Windows when
        # the toplevel loses focus right after being mapped.
        try:
            self.win.protocol("WM_DELETE_WINDOW", self._on_close)
        except Exception:
            pass
        # Do NOT call grab_set() — we want the underlying grid clickable.
        # Center on the parent.
        self.win.update_idletasks()
        try:
            x = master.winfo_rootx() + 80
            y = master.winfo_rooty() + 60
            self.win.geometry(f"+{x}+{y}")
        except Exception:
            pass
        # Force the window above the parent and pull focus to it.
        # Use after() so it runs on the next idle tick — calling lift()
        # and focus_force() synchronously inside __init__ races with the
        # <ButtonRelease-1> event that just triggered us, and on Windows
        # the parent sometimes grabs focus back and the toplevel then
        # receives a synthetic focus-out that looks like "auto close".
        self.win.after(50, self._post_show_focus)

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
    def _post_show_focus(self) -> None:
        """Run after the event loop idles so the toplevel survives the
        <ButtonRelease-1> that opened it. Without this, Windows can
        bounce focus back to the main window during the same event
        dispatch, which on some Tk builds triggers a phantom close."""
        try:
            if not self.win.winfo_exists():
                return
            self.win.lift()
            self.win.focus_force()
        except Exception:
            pass

    def _on_close(self) -> None:
        try:
            self.win.destroy()
        except Exception:
            pass

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

    @staticmethod
    def _s(v: Any) -> str:
        """Coerce any value (including None / int / bytes) to a safe str."""
        if v is None:
            return ""
        if isinstance(v, bytes):
            try:
                return v.decode("utf-8", errors="replace")
            except Exception:
                return ""
        return str(v)

    def _render(self) -> None:
        w = self._current_word()
        if not w:
            try:
                self.word_lbl.configure(text="(无内容)")
            except Exception:
                pass
            return
        word = self._s(w.get("word"))
        phonetic = self._s(w.get("phonetic"))
        translation = _safe_translation(word, self._s(w.get("translation")))
        pos = self._s(w.get("pos"))
        try:
            freq = int(w.get("frequency") or 0)
        except Exception:
            freq = 0
        try:
            stars = int(w.get("star_rating") or 0)
        except Exception:
            stars = 0
        example_en = self._s(w.get("example_sentence"))
        example_zh = self._s(w.get("example_translation"))
        mastered = bool(w.get("mastered"))
        try:
            wrong_count = int(w.get("wrong_count") or 0)
        except Exception:
            wrong_count = 0

        # Title: "word  (5/30)"
        try:
            self.word_lbl.configure(text=f"{word}  ")
            self.phon_lbl.configure(text=phonetic if phonetic else "[/]")
        except Exception:
            return
        # translation
        try:
            self.trans_lbl.configure(
                text=f"{pos}  {translation}" if pos else (translation or "(暂无中文释义)")
            )
        except Exception:
            pass
        # meta
        meta_bits = [
            f"⭐ {stars}/5",
            f"频次: {freq}",
            f"错题: {wrong_count} 次" if wrong_count else None,
        ]
        try:
            self.meta_lbl.configure(text="  ·  ".join(b for b in meta_bits if b))
        except Exception:
            pass
        # examples
        try:
            self.ex_en.configure(state="normal")
            self.ex_en.delete("1.0", "end")
            self.ex_en.insert("1.0", example_en or "(暂无例句)")
            self.ex_en.configure(state="disabled")
            self.ex_zh.configure(text=example_zh)
        except Exception:
            pass
        # mastered checkbox
        try:
            self.mastered_var.set(mastered)
        except Exception:
            pass
        # window title
        try:
            self.win.title(
                f"🔎  {word}  ({self._index + 1}/{len(self.words)})"
            )
        except Exception:
            pass