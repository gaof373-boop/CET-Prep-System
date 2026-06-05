"""🎧 听力板块 — 沉浸式中英对照 + 点击即查词。

设计:
- 顶部"控制条":📁 上一题 / 下一题 / ▶ 播放 / ⏸ 暂停 / ⏮ ⏭ 跳转(10s 间隔)
  · 因为我们没真实音频,音频按钮在没音频时退化为"无音频 · 显示文本"提示
- 下方"对照区":原文字幕 + 同步问题(题目下提供参考译文)
- 沉浸式交互:点击原文中的任何单词,弹"单词详情"弹窗
  (复用 ui.views.word_detail.WordDetailDialog 的接口,但用更轻量版的
   "迷你详情"标签页直接显示;为简化,这里只弹"中文释义 + 音标"标签,
   复用 core.translations.lookup_translation() 提供本地词典兜底)

> 因为数据库没有真实 .mp3 文件,本视图把"无音频"也做成一种合法的状态:
  "听力备考提示" + 文字稿,在主区域以绿色标签提示学生。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from tkinter import StringVar
from typing import Any

import customtkinter as ctk

from core.data_manager import DataManager
from core.translations import lookup_translation
from ui.fonts import ctk_font
from ui.safe import safe_callback, _logger as _log

_log = logging.getLogger("listening_view")


# Pseudo states for the audio control bar
STATE_NO_AUDIO = "no_audio"   # the usual case (no .mp3 in DB)
STATE_PLAYING = "playing"     # user clicked "Play" (no real audio, but cosmetic)
STATE_PAUSED = "paused"


class ListeningView(ctk.CTkFrame):
    SECTION_KEY = "listening"
    SECTION_TITLE = "🎧  听力板块"

    def __init__(self, master, dm: DataManager, ai, level_var: StringVar):
        super().__init__(master, fg_color="transparent")
        self.dm = dm
        self.ai = ai  # kept for future LLM-driven listening features
        self.level_var = level_var
        # audio state (purely visual; we don't have a real .mp3)
        self._audio_state = STATE_NO_AUDIO
        self._position_sec = 0
        self._audio_length_sec = 0
        self._current_audio_path = None
        self._tick_after = None
        self._items: list[dict] = []
        self._current_idx: int = 0
        self._build()
        self.refresh()

    # =====================================================================
    # Layout
    # =====================================================================
    def _build(self) -> None:
        # header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(22, 4))
        ctk.CTkLabel(
            header, text="🎧  听力板块",
            font=ctk_font(size=24, weight="bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            header, text="  ·  中英对照 · 点击查词",
            font=ctk_font(size=12),
            text_color=("gray40", "gray60"),
        ).pack(side="left", padx=8)

        # ====== 极简控制条 ======
        ctrl = ctk.CTkFrame(
            self, corner_radius=10,
            fg_color=("white", "#1F2937"), border_width=1,
        )
        ctrl.pack(fill="x", padx=24, pady=(4, 6))
        # Items: ⏮ 10s | ▶ / ⏸ | ⏭ 10s | progress bar | 状态标签 | 上一题 / 下一题
        ctk.CTkButton(
            ctrl, text="⏮ -10s", width=70, height=32,
            font=ctk_font(size=12),
            command=safe_callback(lambda: self._skip(-10)),
        ).pack(side="left", padx=(10, 4), pady=8)
        self.play_btn = ctk.CTkButton(
            ctrl, text="▶  播放", width=80, height=32,
            font=ctk_font(size=12, weight="bold"),
            command=safe_callback(self._toggle_play),
            fg_color=("#10B981", "#059669"),
            hover_color=("#059669", "#10B981"),
        )
        self.play_btn.pack(side="left", padx=4, pady=8)
        ctk.CTkButton(
            ctrl, text="⏭ +10s", width=70, height=32,
            font=ctk_font(size=12),
            command=safe_callback(lambda: self._skip(+10)),
        ).pack(side="left", padx=4, pady=8)
        # progress (visual only)
        self.progress = ctk.CTkProgressBar(ctrl, height=8, width=320)
        self.progress.set(0.0)
        self.progress.pack(side="left", padx=10, pady=8)
        self.time_lbl = ctk.CTkLabel(
            ctrl, text="00:00 / 00:00", font=ctk_font(size=12),
            text_color=("gray40", "gray60"),
        )
        self.time_lbl.pack(side="left", padx=4, pady=8)
        # status (right side)
        self.status_lbl = ctk.CTkLabel(
            ctrl, text="🎧  无音频文件 · 已显示原文文本",
            font=ctk_font(size=12, weight="bold"),
            text_color=("#F59E0B", "#FBBF24"),
        )
        self.status_lbl.pack(side="right", padx=12, pady=8)
        # nav
        ctk.CTkButton(
            ctrl, text="◀ 上一题", width=90, height=32,
            font=ctk_font(size=12),
            command=safe_callback(self._prev_item),
            fg_color=("#E2E8F0", "#1F2937"),
            text_color=("gray10", "gray90"),
            hover_color=("#CBD5E0", "#334155"),
        ).pack(side="right", padx=2, pady=8)
        ctk.CTkButton(
            ctrl, text="下一题 ▶", width=90, height=32,
            font=ctk_font(size=12),
            command=safe_callback(self._next_item),
            fg_color=("#E2E8F0", "#1F2937"),
            text_color=("gray10", "gray90"),
            hover_color=("#CBD5E0", "#334155"),
        ).pack(side="right", padx=2, pady=8)

        # ====== "无音频" 备考提示条 ======
        self.tip_frame = ctk.CTkFrame(
            self, corner_radius=8,
            fg_color=("#FEF3C7", "#451A03"),
            border_width=1, border_color=("#FCD34D", "#92400E"),
        )
        self.tip_frame.pack(fill="x", padx=24, pady=(0, 6))
        ctk.CTkLabel(
            self.tip_frame,
            text="💡  听力备考提示:本系统暂未配 .mp3 音频文件,你可滚动下方对照文本,"
                 "点击任一单词即时查看释义,并配合官方真题 APP 进行听力训练。",
            font=ctk_font(size=12),
            text_color=("#92400E", "#FDE68A"),
            anchor="w", wraplength=1100, justify="left",
        ).pack(fill="x", padx=14, pady=6)

        # ====== 沉浸式对照区 ======
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=(0, 16))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # Transcript area (click-to-look-up)
        self.trans_box = ctk.CTkTextbox(
            body, wrap="word",
            font=ctk_font(size=14),
        )
        self.trans_box.pack(fill="both", expand=True)
        # Tag styles (no `font` here, no tuple colors — CTk textbox
        # only accepts single strings for tag_config)
        self.trans_box.tag_config("title", foreground="#3B82F6")
        self.trans_box.tag_config("meta", foreground="#6B7280")
        self.trans_box.tag_config("script", foreground="#1E3A8A")
        self.trans_box.tag_config("word", foreground="#1E3A8A", underline=True)
        # The yellow hover style for clickable words is handled by
        # <Enter>/<Leave> bindings in _render_current.
        # Build a tiny pop-up for word lookup (child of this frame so
        # it floats above the textbox).
        self._word_popup = WordLookupPopup(self)

    # =====================================================================
    # Refresh / nav
    # =====================================================================
    def refresh(self) -> None:
        try:
            level = self.level_var.get().replace("-", "")
            self._items = self.dm.list_listening(level)
            if not self._items:
                self._render_empty()
                return
            if self._current_idx >= len(self._items):
                self._current_idx = 0
            self._audio_state = STATE_NO_AUDIO
            self._position_sec = 0
            self._update_control_bar()
            self._render_current()
        except Exception:
            _log.exception("ListeningView.refresh failed")
            self._render_empty()

    def _render_empty(self) -> None:
        self.trans_box.configure(state="normal")
        self.trans_box.delete("1.0", "end")
        self.trans_box.insert("end", "(当前级别暂无听力题)", "meta")
        self.trans_box.configure(state="disabled")
        self.time_lbl.configure(text="00:00 / 00:00")
        self.progress.set(0.0)

    def _render_current(self) -> None:
        item = self._items[self._current_idx]
        self.trans_box.configure(state="normal")
        self.trans_box.delete("1.0", "end")
        title = item.get("section") or f"Item {self._current_idx + 1}"
        year = item.get("year", "?")
        session = item.get("session", "")
        topic = item.get("topic_type", "")
        self.trans_box.insert("end", f"🎙️  {title}\n", "title")
        self.trans_box.insert(
            "end", f"   {year} {session}  ·  {topic}\n\n", "meta")
        # Clickable transcript
        self._insert_clickable(item.get("audio_script", ""))
        self.trans_box.insert("end", "\n\n", "meta")
        # Questions + answers block
        self.trans_box.insert("end", "📝 题目与答案\n", "title")
        try:
            import json
            qs = json.loads(item.get("questions") or "[]")
        except Exception:
            qs = []
        for i, q in enumerate(qs, 1):
            self.trans_box.insert(
                "end", f"   Q{i}. {q.get('q', '')}\n", "meta")
            for opt in q.get("options", []):
                self.trans_box.insert("end", f"      {opt}\n", "meta")
        ans = (item.get("answers") or "").strip()
        if ans:
            self.trans_box.insert("end", f"\n✅ 参考答案: {ans}\n", "meta")
        if item.get("analysis"):
            self.trans_box.insert(
                "end", f"\n💡 解析: {item['analysis']}\n", "meta")
        # Disable editing; clicking is still captured via tag_bind
        self.trans_box.configure(state="disabled")
        # Update control bar time labels
        self._update_time_label()

    def _insert_clickable(self, script: str) -> None:
        """Insert the audio script with each English word as a clickable
        tag. We render word-by-word and bind <Button-1> to the
        underlying index so any click triggers a lookup.
        """
        if not script:
            self.trans_box.insert("end", "(暂无原文)", "meta")
            return
        # Tokenize: split on whitespace, keeping separators
        for tok in re.split(r"(\s+)", script):
            if tok.isspace() or tok == "":
                self.trans_box.insert("end", tok, "script")
                continue
            # Strip surrounding punctuation for click-to-look-up
            m = re.match(r"^([^\w]*)([\w'-]+)([^\w]*)$", tok)
            if not m:
                self.trans_box.insert("end", tok, "script")
                continue
            prefix, word, suffix = m.groups()
            if prefix:
                self.trans_box.insert("end", prefix, "script")
            # Insert the word as a clickable token
            start_index = self.trans_box.index("end-1c")
            self.trans_box.insert("end", word, "word")
            end_index = self.trans_box.index("end-1c")
            tag_name = f"w_{start_index}_{end_index}"
            self.trans_box.tag_add(tag_name, start_index, end_index)
            self.trans_box.tag_config(
                tag_name,
                foreground="#1E3A8A",
                underline=True,
            )
            self.trans_box.tag_bind(
                tag_name, "<Button-1>",
                lambda _e, w=word: self._on_word_click(w),
            )
            if suffix:
                self.trans_box.insert("end", suffix, "script")

    def _on_word_click(self, word: str) -> None:
        """Look up the word in the local dict and pop a small tooltip-like
        window near the click position."""
        # Pull from DB first via a quick query for richer info
        translation, phonetic, example = self._lookup_word(word)
        self._word_popup.show(
            word=word, translation=translation,
            phonetic=phonetic, example=example,
            x=400, y=200,  # roughly centre; CTk doesn't expose pointer pos
        )

    def _lookup_word(self, word: str) -> tuple[str, str, str]:
        """Try DB first (where wiktionary populated fields), then
        fall back to the in-process dictionary."""
        w = word.strip().lower()
        try:
            row = self.dm._conn().execute(  # type: ignore[attr-defined]
                "SELECT translation, phonetic, example_sentence "
                "FROM vocabulary WHERE word = ? LIMIT 1", (w,),
            ).fetchone()
            if row:
                return (
                    row["translation"] or lookup_translation(w) or "(暂无)",
                    row["phonetic"] or "[/]",
                    row["example_sentence"] or "",
                )
        except Exception:
            pass
        return (lookup_translation(w) or "(暂无中文释义)", "[/]", "")

    # =====================================================================
    # Audio control — uses pygame.mixer to play the generated .mp3
    # =====================================================================
    def _resolve_audio_path(self, item: dict) -> Path | None:
        """Resolve the .mp3 file for a DB row.

        Looks at:
            1. item['audio_file'] if it points to an existing file
            2. the conventional database/audio/CETn_YYYY_<id>.mp3 path
        Returns the first hit, or None.
        """
        here = Path(__file__).resolve().parent.parent.parent  # project root
        audio_dir = here / "database" / "audio"
        # 1) explicit DB-stored path
        stored = item.get("audio_file")
        if stored:
            p = Path(stored)
            if not p.is_absolute():
                p = here / stored
            if p.exists():
                return p
        # 2) conventional filename
        level = (item.get("level") or "CET4")
        item_id = item.get("id")
        year = item.get("year") or 0
        candidates = []
        if item_id is not None:
            if year and year != 0:
                candidates.append(audio_dir / f"{level}_{year}_{item_id}.mp3")
            candidates.append(audio_dir / f"{level}_all_{item_id}.mp3")
        for c in candidates:
            if c.exists():
                return c
        return None
        audio_dir = here / "database" / "audio"
        # 1) explicit DB-stored path
        stored = item.get("audio_file")
        if stored:
            p = Path(stored)
            if not p.is_absolute():
                p = here / stored
            if p.exists():
                return p
        # 2) conventional filename
        level = (item.get("level") or "CET4")
        item_id = item.get("id")
        year = item.get("year") or 0
        candidates = []
        if item_id is not None:
            if year and year != 0:
                candidates.append(audio_dir / f"{level}_{year}_{item_id}.mp3")
            candidates.append(audio_dir / f"{level}_all_{item_id}.mp3")
        for c in candidates:
            if c.exists():
                return c
        return None

    def _toggle_play(self) -> None:
        if not self._items:
            return
        item = self._items[self._current_idx]
        if self._audio_state == STATE_PLAYING:
            self._audio_pause()
        else:
            self._audio_play(item)
        self._update_control_bar()

    def _audio_play(self, item: dict) -> None:
        try:
            import pygame
        except ImportError:
            self.status_lbl.configure(
                text="❌ 未安装 pygame 库,无法播放音频",
                text_color=("#EF4444", "#F87171"),
            )
            return
        path = self._resolve_audio_path(item)
        if path is None:
            self.status_lbl.configure(
                text="❌ 本题暂无 .mp3 音频,请运行 generate_listening_audio",
                text_color=("#EF4444", "#F87171"),
            )
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.play()
            self._current_audio_path = path
            self._audio_length_sec = self._probe_audio_length(path)
            self._audio_state = STATE_PLAYING
            self._start_tick()
        except Exception as e:
            self.status_lbl.configure(
                text=f"❌ 播放失败: {e}",
                text_color=("#EF4444", "#F87171"),
            )

    def _audio_pause(self) -> None:
        try:
            import pygame
            if pygame.mixer.music.get_busy() or pygame.mixer.music.get_pos() >= 0:
                pygame.mixer.music.pause()
        except Exception:
            pass
        self._audio_state = STATE_PAUSED
        self._stop_tick()

    def _audio_unpause(self) -> None:
        try:
            import pygame
            pygame.mixer.music.unpause()
        except Exception:
            pass
        self._audio_state = STATE_PLAYING
        self._start_tick()

    def _audio_stop(self) -> None:
        try:
            import pygame
            pygame.mixer.music.stop()
        except Exception:
            pass
        self._audio_state = STATE_NO_AUDIO
        self._position_sec = 0
        self._stop_tick()
        self._update_time_label()
        self._update_control_bar()

    @staticmethod
    def _probe_audio_length(path: Path) -> float:
        """Best-effort MP3 duration lookup using mutagen; returns 0 on
        any error. Returns seconds."""
        try:
            from mutagen.mp3 import MP3
            audio = MP3(str(path))
            return float(audio.info.length)
        except Exception:
            return 0.0

    # ---- playhead ticker (a 0.5s tick that advances the progress bar) ----
    def _start_tick(self) -> None:
        try:
            import pygame
            # initialise position from mixer
            ms = pygame.mixer.music.get_pos()
            if ms and ms > 0:
                self._position_sec = ms / 1000.0
        except Exception:
            pass
        self._schedule_tick()

    def _schedule_tick(self) -> None:
        try:
            self._tick_after = self.after(500, self._on_tick)
        except Exception:
            self._tick_after = None

    def _stop_tick(self) -> None:
        if getattr(self, "_tick_after", None):
            try:
                self.after_cancel(self._tick_after)
            except Exception:
                pass
            self._tick_after = None

    def _on_tick(self) -> None:
        try:
            import pygame
            if not pygame.mixer.music.get_busy():
                # playback ended naturally
                self._position_sec = self._audio_length_sec or self._position_sec
                self._update_time_label()
                self._audio_state = STATE_NO_AUDIO
                self._update_control_bar()
                return
            ms = pygame.mixer.music.get_pos()
            if ms is not None and ms >= 0:
                self._position_sec = ms / 1000.0
            self._update_time_label()
        except Exception:
            pass
        if self._audio_state == STATE_PLAYING:
            self._schedule_tick()

    def _skip(self, delta: int) -> None:
        if not self._items:
            return
        item = self._items[self._current_idx]
        path = self._resolve_audio_path(item)
        # If audio is loaded, use real seek (pygame doesn't support
        # direct seek on MP3, so we restart from offset).
        if path is not None and self._audio_state != STATE_NO_AUDIO:
            self._audio_pause()
            self._position_sec = max(
                0, min(self._position_sec + delta, self._audio_length_sec or 1e9))
            try:
                import pygame
                pygame.mixer.music.play(start=self._position_sec)
                self._audio_state = STATE_PLAYING
                self._start_tick()
            except Exception:
                pass
        else:
            # cosmetic-only (no real audio loaded)
            self._position_sec = max(0, self._position_sec + delta)
            self._update_time_label()
            if delta > 0 and self._audio_state == STATE_NO_AUDIO:
                self._audio_play(item)

    def _update_control_bar(self) -> None:
        if self._audio_state == STATE_PLAYING:
            self.play_btn.configure(text="⏸  暂停")
            self.status_lbl.configure(
                text="🎧  正在播放",
                text_color=("#10B981", "#34D399"),
            )
        elif self._audio_state == STATE_PAUSED:
            self.play_btn.configure(text="▶  继续")
            self.status_lbl.configure(
                text="⏸  已暂停",
                text_color=("#F59E0B", "#FBBF24"),
            )
        else:
            self.play_btn.configure(text="▶  播放")
            # check if we have audio file for current item
            has_audio = False
            try:
                if self._items:
                    has_audio = self._resolve_audio_path(
                        self._items[self._current_idx]) is not None
            except Exception:
                pass
            if has_audio:
                self.status_lbl.configure(
                    text="🎧  音频就绪 · 点击播放",
                    text_color=("#10B981", "#34D399"),
                )
            else:
                self.status_lbl.configure(
                    text="🎧  本题暂无 .mp3 · 仅显示文本",
                    text_color=("#F59E0B", "#FBBF24"),
                )

    def _update_time_label(self) -> None:
        pos = max(0, int(self._position_sec))
        total = max(int(self._audio_length_sec or 0), pos, 1)
        # If we have no real length, show the cosmetic total of 180s
        if not self._audio_length_sec:
            total = 180
        self.time_lbl.configure(
            text=f"{pos // 60:02d}:{pos % 60:02d} / {total // 60:02d}:{total % 60:02d}"
        )
        try:
            self.progress.set(min(1.0, pos / total))
        except Exception:
            pass

    def _update_control_bar_legacy_compat(self) -> None:  # not used, kept as hook
        self._update_control_bar()

    @safe_callback
    def _prev_item(self) -> None:
        if self._current_idx > 0:
            self._current_idx -= 1
            self._audio_state = STATE_NO_AUDIO
            self._position_sec = 0
            self._update_control_bar()
            self._render_current()

    @safe_callback
    def _next_item(self) -> None:
        if self._current_idx < len(self._items) - 1:
            self._current_idx += 1
            self._audio_state = STATE_NO_AUDIO
            self._position_sec = 0
            self._update_control_bar()
            self._render_current()


# ---------------------------------------------------------------------------
# Inline word-lookup popup (lightweight, non-modal)
# ---------------------------------------------------------------------------
class WordLookupPopup(ctk.CTkFrame):
    def __init__(self, master: ctk.CTkBaseClass):
        super().__init__(master, corner_radius=8,
                         fg_color=("#FFFBEB", "#1F2937"),
                         border_width=1, border_color=("#F59E0B", "#F59E0B"))
        # Initially hidden via place_forget; shown on demand
        self.place_forget()
        self._build_static()

    def _build_static(self) -> None:
        self.word_lbl = ctk.CTkLabel(
            self, text="", font=ctk_font(size=18, weight="bold"),
            text_color=("#1E3A8A", "#60A5FA"),
        )
        self.word_lbl.pack(anchor="w", padx=12, pady=(8, 2))
        self.phon_lbl = ctk.CTkLabel(
            self, text="", font=ctk_font(size=12),
            text_color=("gray40", "gray60"),
        )
        self.phon_lbl.pack(anchor="w", padx=12)
        self.trans_lbl = ctk.CTkLabel(
            self, text="", font=ctk_font(size=13),
            text_color=("#10B981", "#34D399"),
            wraplength=320, justify="left", anchor="w",
        )
        self.trans_lbl.pack(fill="x", padx=12, pady=(2, 4))
        self.ex_lbl = ctk.CTkLabel(
            self, text="", font=ctk_font(size=11),
            text_color=("gray20", "gray80"),
            wraplength=320, justify="left", anchor="w",
        )
        self.ex_lbl.pack(fill="x", padx=12, pady=(0, 8))

    def show(self, *, word: str, translation: str, phonetic: str,
             example: str, x: int, y: int) -> None:
        self.word_lbl.configure(text=word)
        self.phon_lbl.configure(text=phonetic or "[/]")
        self.trans_lbl.configure(text=translation or "(暂无中文释义)")
        self.ex_lbl.configure(
            text=f"📌 {example}" if example else "📌 (暂无例句)"
        )
        # Position near top-right of the listening view
        try:
            master = self.master
            self.place(in_=master, relx=0.66, rely=0.18)
        except Exception:
            self.place(x=x, y=y)
        # Auto-fade after 4s if not interacted with
        try:
            self.after(4000, lambda: self.place_forget())
        except Exception:
            pass