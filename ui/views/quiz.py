"""背单词自测板块:50/50 双向题,基于已"掌握"词随机抽样。

- 抽测范围:仅从 ``mastered=1`` 的词里取
- 50% 概率显示英文(用户输入中文) / 50% 概率显示中文(用户拼英文)
- 判分:
  - 正确 → 高亮绿色
  - 错误 → 高亮红色,展示音标/中文/例句
  - 错误同时调用 :func:`DataManager.record_wrong` 计数
  - 正确调用 :func:`DataManager.record_correct`;连续 2 次自动移出错题本
- 没有可抽测词时给出友好提示
"""

from __future__ import annotations

import logging
import random
import re
from tkinter import StringVar
from typing import Any

import customtkinter as ctk

from core.data_manager import DataManager
from core.translations import lookup_translation
from ui.fonts import ctk_font
from ui.safe import safe_callback, _logger as _log

_log = logging.getLogger("quiz_view")

WORDS_PER_SESSION = 10


def _norm(s: str) -> str:
    """Normalize an answer for fuzzy comparison.

    - lowercase
    - strip leading/trailing whitespace and common punctuation
    - collapse multiple spaces
    """
    if not s:
        return ""
    s = s.strip().lower()
    s = re.sub(r"[\s,;.!?\"'()\[\]{}]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _check_english(user: str, expected: str) -> bool:
    """Lenient English answer check.

    Accept if either:
    - Exact match after normalization, OR
    - Both words share the same first 4 characters
    """
    u = _norm(user)
    e = _norm(expected)
    if not u or not e:
        return False
    if u == e:
        return True
    # Prefix-tolerant (handles "appease" vs "appeasement" etc.)
    if len(e) >= 4 and u[:4] == e[:4]:
        return True
    return False


def _check_chinese(user: str, expected: str) -> bool:
    """Chinese answer check: every char of user must appear in expected.

    - The first semicolon-separated segment of ``expected`` is treated
      as the "primary" translation; matching any of its characters is
      a 50% pass; matching all of them is a 100% pass.
    - For simplicity we accept if the user's normalized string
      contains the expected string OR vice-versa.
    """
    u = _norm(user)
    e = _norm(expected)
    if not u or not e:
        return False
    if u == e:
        return True
    # substring match in either direction
    if u in e or e in u:
        return True
    # character-coverage heuristic
    set_u = set(c for c in u if "一" <= c <= "鿿")
    set_e = set(c for c in e if "一" <= c <= "鿿")
    if not set_e:
        return False
    coverage = len(set_u & set_e) / len(set_e)
    return coverage >= 0.6  # 60% of expected Chinese chars must be in user input


class QuizView(ctk.CTkFrame):
    SECTION_KEY = "quiz"
    SECTION_TITLE = "🎲  背单词自测"

    def __init__(self, master, dm: DataManager, level_var: StringVar):
        super().__init__(master, fg_color="transparent")
        self.dm = dm
        self.level_var = level_var
        # session state
        self.questions: list[dict[str, Any]] = []
        self.current_idx = 0
        self.session_stats = {"right": 0, "wrong": 0}
        self._build()
        self.refresh()

    # ---------- layout ----------
    def _build(self) -> None:
        # header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(22, 6))
        ctk.CTkLabel(
            header, text="🎲  背单词自测",
            font=ctk_font(size=24, weight="bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            header, text="  ·  50/50 双向抽测 (英→中 / 中→英)",
            font=ctk_font(size=12),
            text_color=("gray40", "gray60"),
        ).pack(side="left")

        # info banner
        self.info_lbl = ctk.CTkLabel(
            self, text="",
            font=ctk_font(size=12),
            text_color=("gray40", "gray60"),
            anchor="w",
        )
        self.info_lbl.pack(fill="x", padx=24, pady=(0, 6))

        # main "card" frame
        self.card = ctk.CTkFrame(
            self, corner_radius=14, border_width=1,
            fg_color=("white", "#1F2937"),
        )
        self.card.pack(fill="both", expand=True, padx=24, pady=(6, 12))
        # progress + counters
        head = ctk.CTkFrame(self.card, fg_color="transparent")
        head.pack(fill="x", padx=18, pady=(14, 4))
        self.progress_lbl = ctk.CTkLabel(
            head, text="",
            font=ctk_font(size=13, weight="bold"),
            text_color=("gray40", "gray60"),
        )
        self.progress_lbl.pack(side="left")
        self.score_lbl = ctk.CTkLabel(
            head, text="", font=ctk_font(size=13, weight="bold"),
        )
        self.score_lbl.pack(side="right")

        # prompt
        self.prompt_lbl = ctk.CTkLabel(
            self.card, text="点击「开始新一轮」进入自测",
            font=ctk_font(size=20, weight="bold"),
            text_color=("#3B82F6", "#60A5FA"),
            wraplength=700, justify="center",
        )
        self.prompt_lbl.pack(pady=(30, 8))

        self.hint_lbl = ctk.CTkLabel(
            self.card, text="",
            font=ctk_font(size=12),
            text_color=("gray40", "gray60"),
            wraplength=700, justify="center",
        )
        self.hint_lbl.pack(pady=(0, 10))

        # input row
        input_row = ctk.CTkFrame(self.card, fg_color="transparent")
        input_row.pack(pady=(10, 6))
        self.answer_var = StringVar()
        self.answer_entry = ctk.CTkEntry(
            input_row, textvariable=self.answer_var, width=400, height=42,
            placeholder_text="在此输入你的答案…",
            font=ctk_font(size=15),
        )
        self.answer_entry.pack(side="left", padx=8)
        self.answer_entry.bind("<Return>", safe_callback(lambda _e: self._on_submit()))

        ctk.CTkButton(
            input_row, text="提交", width=90, height=42,
            command=safe_callback(self._on_submit),
            font=ctk_font(size=14, weight="bold"),
            fg_color=("#10B981", "#059669"),
            hover_color=("#059669", "#10B981"),
        ).pack(side="left", padx=4)

        # feedback area
        self.feedback_frame = ctk.CTkFrame(self.card, fg_color="transparent")
        self.feedback_frame.pack(fill="x", padx=18, pady=(8, 4))
        self.feedback_lbl = ctk.CTkLabel(
            self.feedback_frame, text="",
            font=ctk_font(size=14, weight="bold"),
            wraplength=760, justify="left", anchor="w",
        )
        self.feedback_lbl.pack(fill="x")
        self.detail_lbl = ctk.CTkLabel(
            self.feedback_frame, text="",
            font=ctk_font(size=12),
            text_color=("gray20", "gray80"),
            wraplength=760, justify="left", anchor="w",
        )
        self.detail_lbl.pack(fill="x", pady=(4, 0))

        # bottom buttons
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=24, pady=(0, 18))
        ctk.CTkButton(
            bottom, text="🔄 开始新一轮",
            height=40, width=160,
            font=ctk_font(size=13, weight="bold"),
            command=safe_callback(self._new_session),
            fg_color=("#3B82F6", "#3B82F6"),
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            bottom, text="⏭ 跳过本题",
            height=40, width=120,
            font=ctk_font(size=13),
            command=safe_callback(self._skip),
            fg_color=("#E2E8F0", "#2D3748"),
            text_color=("gray10", "gray90"),
            hover_color=("#CBD5E0", "#334155"),
        ).pack(side="left", padx=4)

    # ---------- lifecycle ----------
    def refresh(self) -> None:
        """Update info banner. Doesn't start a session — user must
        click '开始新一轮' to begin."""
        try:
            level = self.level_var.get().replace("-", "")
            n_mastered = self.dm.count_mastered(level)
            n_wrong = self.dm.count_wrong(level)
            self.info_lbl.configure(
                text=f"当前 {level}  ·  已掌握 {n_mastered} 词 (题库来源)  ·  错题本 {n_wrong} 词"
            )
        except Exception:
            _log.exception("QuizView.refresh failed")
            self.info_lbl.configure(text="(统计信息加载失败)")

    def _new_session(self) -> None:
        try:
            level = self.level_var.get().replace("-", "")
            pool = self.dm.list_mastered(level, limit=2000)
            if len(pool) < 4:
                self.prompt_lbl.configure(
                    text="题库不足",
                    text_color=("#EF4444", "#F87171"),
                )
                self.hint_lbl.configure(
                    text=f"你需要至少 4 个'已掌握'的词才能开始自测。\n"
                         f"请到词汇板块,点击感兴趣的单词卡片,然后在弹窗里勾上'✓ 已掌握'。\n"
                         f"当前 {level} 已掌握 {len(pool)} 词。",
                )
                self.questions = []
                return
            n = min(WORDS_PER_SESSION, len(pool))
            self.questions = random.sample(pool, n)
            for q in self.questions:
                q["direction"] = "en2zh" if random.random() < 0.5 else "zh2en"
            self.current_idx = 0
            self.session_stats = {"right": 0, "wrong": 0}
            self._render_question()
        except Exception:
            _log.exception("_new_session failed")

    # ---------- question rendering ----------
    def _render_question(self) -> None:
        if not self.questions:
            return
        if self.current_idx >= len(self.questions):
            self._show_summary()
            return
        q = self.questions[self.current_idx]
        # progress
        self.progress_lbl.configure(
            text=f"第 {self.current_idx + 1}/{len(self.questions)} 题"
        )
        self.score_lbl.configure(
            text=f"✓ {self.session_stats['right']}    ✗ {self.session_stats['wrong']}",
            text_color=("#10B981", "#34D399"),
        )
        # feedback area cleared
        self.feedback_lbl.configure(text="", text_color=("gray20", "gray80"))
        self.detail_lbl.configure(text="")
        # prompt
        if q["direction"] == "en2zh":
            prompt = q.get("word", "")
            hint = f"音标: {q.get('phonetic') or '[/]'}    请输入中文释义"
        else:
            prompt = _norm(q.get("translation", "")).split(" ")[0]  # primary zh gloss
            fb = lookup_translation(q.get("word", ""))
            if not prompt and fb:
                prompt = _norm(fb).split(" ")[0]
            hint = f"请拼出英文单词    提示: {len(q.get('word', ''))} 个字母"
        self.prompt_lbl.configure(
            text=prompt,
            text_color=("#1E3A8A" if q["direction"] == "en2zh" else "#3B82F6",
                        "#93C5FD" if q["direction"] == "en2zh" else "#60A5FA"),
        )
        self.hint_lbl.configure(text=hint)
        # clear input + focus
        self.answer_var.set("")
        try:
            self.answer_entry.focus_set()
        except Exception:
            pass

    # ---------- judging ----------
    def _on_submit(self) -> None:
        if not self.questions or self.current_idx >= len(self.questions):
            return
        q = self.questions[self.current_idx]
        user = self.answer_var.get()
        if q["direction"] == "en2zh":
            correct = _check_chinese(user, q.get("translation", ""))
        else:
            correct = _check_english(user, q.get("word", ""))
        try:
            if correct:
                consec, removed = self.dm.record_correct(q["id"])
                self.session_stats["right"] += 1
                self.feedback_lbl.configure(
                    text="✅ 正确!",
                    text_color=("#10B981", "#34D399"),
                )
                if removed:
                    self.feedback_lbl.configure(
                        text=f"✅ 正确!  (连续 2 次答对,已自动从错题本移除)",
                        text_color=("#10B981", "#34D399"),
                    )
            else:
                self.dm.record_wrong(q["id"])
                self.session_stats["wrong"] += 1
                self.feedback_lbl.configure(
                    text="❌ 错误",
                    text_color=("#EF4444", "#F87171"),
                )
            # show the answer / phonetic / example
            self._show_feedback(q)
            # auto-advance after a short delay
            self.after(1400, safe_callback(self._next_question))
        except Exception:
            _log.exception("_on_submit failed")

    def _skip(self) -> None:
        if not self.questions or self.current_idx >= len(self.questions):
            return
        try:
            self.session_stats["wrong"] += 1
            q = self.questions[self.current_idx]
            self.dm.record_wrong(q["id"])
            self.feedback_lbl.configure(
                text="⏭ 跳过 (记为错题)",
                text_color=("#F59E0B", "#FBBF24"),
            )
            self._show_feedback(q)
            self.after(1100, safe_callback(self._next_question))
        except Exception:
            _log.exception("_skip failed")

    def _next_question(self) -> None:
        self.current_idx += 1
        self._render_question()

    # ---------- summary ----------
    def _show_summary(self) -> None:
        n = self.session_stats["right"] + self.session_stats["wrong"]
        pct = (self.session_stats["right"] / n * 100) if n else 0
        self.prompt_lbl.configure(
            text=f"🎉 本轮完成! 正确率 {pct:.0f}%",
            text_color=("#10B981", "#34D399"),
        )
        self.hint_lbl.configure(
            text=f"✓ 答对 {self.session_stats['right']}   ·   ✗ 答错 {self.session_stats['wrong']}   ·   共 {n} 题\n"
                 f"可以点击「开始新一轮」继续练习,或到「错题本」巩固。"
        )
        self.progress_lbl.configure(text="")
        self.score_lbl.configure(text="")
        self.feedback_lbl.configure(text="", text_color=("gray20", "gray80"))
        self.detail_lbl.configure(text="")
        # refresh info banner (counts may have changed)
        self.refresh()

    def _show_feedback(self, q: dict) -> None:
        """After judging, show the canonical answer + extra hints."""
        word = q.get("word", "")
        phonetic = q.get("phonetic") or "[/]"
        translation = q.get("translation") or "(暂无中文释义)"
        example = q.get("example_sentence") or ""
        example_zh = q.get("example_translation") or ""
        # layout: 3 lines
        line1 = f"📌 答案: {word}  {phonetic}"
        line2 = f"📖 中文: {translation}"
        line3 = f"📚 例句: {example}    {example_zh}" if example else ""
        self.detail_lbl.configure(text=line1 + "\n" + line2 + ("\n" + line3 if line3 else ""))
