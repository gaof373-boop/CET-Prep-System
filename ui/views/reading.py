"""阅读板块 — 左右分栏 + 答题交互 + 红绿判分 + AI 高仿。

布局:
    ┌────────────────┬───────────────────────────┐
    │ 📄 Passage     │ 📝 Questions (5 道)        │
    │ (左栏,可滚动) │ (右栏,可滚动)            │
    │                │ Q1 ○ A ○ B ○ C ○ D       │
    │                │ Q2 ...                   │
    │                │ Q3 ...                   │
    │                │ Q4 ...                   │
    │                │ Q5 ...                   │
    │                │ [📝 提交并对答案]        │
    │                │ (判分后:对绿,错红+解析) │
    │ [✨ AI 高仿生成] (顶栏按钮)            │
    └────────────────┴───────────────────────────┘

每次进入板块,默认显示该级别第一篇真题;侧边栏上方"历年真题"列表
支持点击切换。
"""

from __future__ import annotations

import json
import logging
import threading
from tkinter import StringVar
from typing import Any

import customtkinter as ctk

from core.ai_service import AIService
from core.data_manager import DataManager
from ui.fonts import ctk_font
from ui.safe import safe_callback, _logger as _log

_log = logging.getLogger("reading_view")


# A→index helper
LETTERS = ["A", "B", "C", "D"]


class ReadingView(ctk.CTkFrame):
    SECTION_KEY = "reading"
    SECTION_TITLE = "📖  阅读板块"

    def __init__(self, master, dm: DataManager, ai: AIService, level_var: StringVar):
        super().__init__(master, fg_color="transparent")
        self.dm = dm
        self.ai = ai
        self.level_var = level_var

        # current source row (dict) for AI 高仿
        self._current_source: dict[str, Any] | None = None
        # generated AI reading (dict with title/passage/questions/answers)
        self._ai_extras: list[dict[str, Any]] = []  # AI-generated items in this session
        # the displayed item index (across the natural list + AI extras)
        self._items: list[dict[str, Any]] = []
        self._current_idx: int = 0
        # user answers, keyed by question index
        self._user_answers: dict[int, str] = {}
        # whether the user has already submitted for the current item
        self._submitted: bool = False
        # guard for AI thread
        self._ai_running: bool = False

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
            header, text="📖  阅读板块",
            font=ctk_font(size=24, weight="bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            header, text="  ·  左右分栏 · 红绿判分 · AI 高仿",
            font=ctk_font(size=12),
            text_color=("gray40", "gray60"),
        ).pack(side="left", padx=8)

        # "AI 高仿" button at the top right
        self.ai_btn = ctk.CTkButton(
            header, text="✨ AI 生成相似阅读 (同题材同难度)",
            height=34, width=240,
            font=ctk_font(size=12, weight="bold"),
            fg_color=("#8B5CF6", "#7C3AED"),
            hover_color=("#7C3AED", "#8B5CF6"),
            command=safe_callback(self._start_ai_similar),
        )
        self.ai_btn.pack(side="right", padx=4)

        # status / loading label
        self.status_lbl = ctk.CTkLabel(
            self, text="",
            font=ctk_font(size=12),
            text_color=("gray40", "gray60"),
            anchor="w",
        )
        self.status_lbl.pack(fill="x", padx=24, pady=(2, 4))

        # two-column paned area
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=(4, 12))
        body.grid_columnconfigure(0, weight=1, uniform="reading")
        body.grid_columnconfigure(1, weight=1, uniform="reading")
        body.grid_rowconfigure(0, weight=1)

        # ---------- LEFT: passage ----------
        self.left = ctk.CTkFrame(
            body, corner_radius=10,
            fg_color=("white", "#1F2937"), border_width=1,
        )
        self.left.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=0)
        ctk.CTkLabel(
            self.left, text="📄 仔细阅读",
            font=ctk_font(size=14, weight="bold"), anchor="w",
        ).pack(fill="x", padx=14, pady=(10, 2))
        self.passage_box = ctk.CTkTextbox(
            self.left, wrap="word",
            font=ctk_font(size=14),
        )
        self.passage_box.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        # ---------- RIGHT: questions + submit ----------
        self.right = ctk.CTkScrollableFrame(body, label_text="📝 题目与判分")
        self.right.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=0)

        # Bottom: submit + nav buttons (stick to bottom of right column)
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=24, pady=(0, 14))
        ctk.CTkButton(
            bottom, text="◀ 上一题",
            height=36, width=110,
            font=ctk_font(size=12),
            command=safe_callback(self._prev_item),
            fg_color=("#E2E8F0", "#1F2937"),
            text_color=("gray10", "gray90"),
            hover_color=("#CBD5E0", "#334155"),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            bottom, text="下一题 ▶",
            height=36, width=110,
            font=ctk_font(size=12),
            command=safe_callback(self._next_item),
            fg_color=("#E2E8F0", "#1F2937"),
            text_color=("gray10", "gray90"),
            hover_color=("#CBD5E0", "#334155"),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            bottom, text="🔄 重做本题",
            height=36, width=110,
            font=ctk_font(size=12),
            command=safe_callback(self._reset_current),
            fg_color=("#E2E8F0", "#1F2937"),
            text_color=("gray10", "gray90"),
            hover_color=("#CBD5E0", "#334155"),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            bottom, text="✅ 提交并对答案",
            height=38, width=180,
            font=ctk_font(size=13, weight="bold"),
            command=safe_callback(self._submit_answers),
            fg_color=("#10B981", "#059669"),
            hover_color=("#059669", "#10B981"),
        ).pack(side="right", padx=2)

        # header line with item index
        self.nav_lbl = ctk.CTkLabel(
            bottom, text="",
            font=ctk_font(size=12),
            text_color=("gray40", "gray60"),
        )
        self.nav_lbl.pack(side="right", padx=8)

    # =====================================================================
    # Refresh
    # =====================================================================
    def refresh(self) -> None:
        try:
            level = self.level_var.get().replace("-", "")
            natural = self.dm.list_reading(level)
            # natural list first, then any AI-generated extras from this session
            self._items = list(natural) + list(self._ai_extras)
            if not self._items:
                self._render_empty()
                return
            if self._current_idx >= len(self._items):
                self._current_idx = 0
            self._render_current()
        except Exception:
            _log.exception("ReadingView.refresh failed")
            self._render_empty()

    def _render_empty(self) -> None:
        for w in self.right.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self.right, text="(当前级别暂无阅读题,可点击右上角 ✨ 让 AI 现场生成)",
            font=ctk_font(size=13),
            text_color=("gray40", "gray60"),
            pady=40,
        ).pack()
        self.passage_box.configure(state="normal")
        self.passage_box.delete("1.0", "end")
        self.passage_box.insert("1.0", "(暂无内容)")
        self.passage_box.configure(state="disabled")
        self.nav_lbl.configure(text="0 / 0")

    def _render_current(self) -> None:
        item = self._items[self._current_idx]
        self._current_source = item
        # ---------- passage ----------
        self.passage_box.configure(state="normal")
        self.passage_box.delete("1.0", "end")
        title = item.get("passage_title") or item.get("title") or ""
        passage = item.get("passage") or ""
        year = item.get("year", "?")
        session = item.get("session", "")
        topic = item.get("topic_type", "")
        if title:
            self.passage_box.insert("end", f"📄  {title}\n")
        if year and year != "?":
            self.passage_box.insert(
                "end", f"   {year} {session}  ·  {topic}\n\n")
        self.passage_box.insert("end", passage)
        self.passage_box.configure(state="disabled")
        # ---------- questions ----------
        for w in self.right.winfo_children():
            w.destroy()
        self._user_answers = {}
        self._submitted = False
        # parse questions: could be JSON list (new) or string (old)
        qs = self._parse_questions(item)
        for i, q in enumerate(qs):
            self._build_question_widget(i, q)
        # nav label
        self.nav_lbl.configure(
            text=f"第 {self._current_idx + 1}/{len(self._items)} 题"
        )

    @staticmethod
    def _parse_questions(item: dict) -> list[dict]:
        """Read questions from either the new ``questions`` JSON column
        or the legacy ``options`` JSON column."""
        for key in ("questions", "options"):
            raw = item.get(key)
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                    # Normalize keys: support both {q, options, answer}
                    # and {q, options} (old format) and the
                    # answering_string item.get("answer")
                    out = []
                    for q in parsed:
                        opts = q.get("options") or []
                        # strip leading "A. " etc for clean rendering
                        clean_opts = []
                        for o in opts:
                            text = str(o).strip()
                            # Remove leading "A. " / "B) " / "A:" etc
                            text = re.sub(r"^[A-D][\.\):、]\s*", "", text)
                            clean_opts.append(text)
                        out.append({
                            "q": q.get("q", q.get("question", "(无题目)")),
                            "options": clean_opts,
                            "answer": q.get("answer", ""),
                            "analysis": q.get("analysis", ""),
                        })
                    return out
            except Exception:
                continue
        # legacy: parse from "answers" field (1. B  2. C  3. A ... format)
        ans_text = (item.get("answers") or "").strip()
        if ans_text:
            matches = re.findall(r"(\d+)\.\s*([A-D])", ans_text)
            if matches:
                ans_map = {int(k) - 1: v for k, v in matches}
                # We need actual question text — fall back to analysis
                analysis = item.get("analysis", "")
                # Each question is in the analysis block; pull as best-effort
                return [
                    {"q": f"Question {k + 1}",
                     "options": ["", "", "", ""],
                     "answer": v,
                     "analysis": analysis}
                    for k, v in ans_map.items()
                ]
        return []

    def _build_question_widget(self, q_index: int, q: dict) -> None:
        outer = ctk.CTkFrame(self.right, corner_radius=8,
                             fg_color=("gray95", "#1F2937"),
                             border_width=1,
                             border_color=("#E2E8F0", "#374151"))
        outer.pack(fill="x", padx=8, pady=8)
        # question prompt
        ctk.CTkLabel(
            outer, text=f"Q{q_index + 1}.  {q.get('q', '')}",
            font=ctk_font(size=14, weight="bold"),
            anchor="w", wraplength=520, justify="left",
        ).pack(fill="x", padx=10, pady=(8, 4))
        # ABCD radios
        opt_frame = ctk.CTkFrame(outer, fg_color="transparent")
        opt_frame.pack(fill="x", padx=10, pady=(0, 6))
        self._q_vars: dict[int, StringVar] = getattr(self, "_q_vars", {})
        if q_index not in self._q_vars:
            self._q_vars[q_index] = StringVar(value="")
        var = self._q_vars[q_index]
        opts = q.get("options") or []
        for i, opt in enumerate(opts):
            letter = LETTERS[i] if i < 4 else "?"
            r = ctk.CTkRadioButton(
                opt_frame, text=f"{letter}. {opt or '(无选项)'}",
                variable=var, value=letter,
                font=ctk_font(size=13),
                command=safe_callback(
                    lambda qi=q_index: self._on_radio_change(qi)),
            )
            r.pack(anchor="w", padx=4, pady=2)
            # Stash the radio widget for later highlight
            r._q_index = q_index
            r._letter = letter
            if not hasattr(self, "_radios"):
                self._radios = []
            self._radios.append(r)
        # analysis (hidden until submit)
        analysis = q.get("analysis") or ""
        analysis_lbl = ctk.CTkLabel(
            outer, text="",
            font=ctk_font(size=12),
            text_color=("#10B981", "#34D399"),
            wraplength=520, justify="left", anchor="w",
        )
        analysis_lbl.pack(fill="x", padx=10, pady=(0, 8))
        # Stash for the submit handler
        if not hasattr(self, "_analysis_lbls"):
            self._analysis_lbls = {}
        self._analysis_lbls[q_index] = analysis_lbl
        if not hasattr(self, "_question_meta"):
            self._question_meta = {}
        self._question_meta[q_index] = q

    # =====================================================================
    # Interactions
    # =====================================================================
    def _on_radio_change(self, q_index: int) -> None:
        try:
            self._user_answers[q_index] = self._q_vars[q_index].get()
        except Exception:
            _log.exception("radio change handler failed")

    @safe_callback
    def _prev_item(self) -> None:
        if self._current_idx > 0:
            self._current_idx -= 1
            self._render_current()

    @safe_callback
    def _next_item(self) -> None:
        if self._current_idx < len(self._items) - 1:
            self._current_idx += 1
            self._render_current()

    @safe_callback
    def _reset_current(self) -> None:
        self._render_current()

    @safe_callback
    def _submit_answers(self) -> None:
        if not self._items:
            return
        if self._submitted:
            return
        # Determine correct answers from question meta (after re-parse).
        meta = getattr(self, "_question_meta", {})
        if not meta:
            return
        correct = 0
        total = 0
        for qi, q in meta.items():
            total += 1
            ans = q.get("answer", "").strip().upper()[:1]
            user = self._user_answers.get(qi, "")
            if user == ans:
                correct += 1
        # Visualise the radios
        for r in getattr(self, "_radios", []):
            qi = getattr(r, "_q_index", None)
            letter = getattr(r, "_letter", "")
            if qi is None or letter == "":
                continue
            ans = meta.get(qi, {}).get("answer", "").strip().upper()[:1]
            user = self._user_answers.get(qi, "")
            if not user:
                continue  # un-answered: leave default look
            if user == ans:
                # correct → green
                r.configure(
                    text_color=("#10B981", "#34D399"),
                    fg_color=("#D1FAE5", "#064E3B"),
                    hover_color=("#A7F3D0", "#065F46"),
                )
            else:
                # wrong → red; also mark the correct one green
                r.configure(
                    text_color=("#EF4444", "#FCA5A5"),
                    fg_color=("#FEE2E2", "#7F1D1D"),
                    hover_color=("#FECACA", "#991B1B"),
                )
        # Reveal the analysis for each question
        for qi, lbl in getattr(self, "_analysis_lbls", {}).items():
            q = meta.get(qi, {})
            ans = q.get("answer", "").strip().upper()[:1]
            user = self._user_answers.get(qi, "未作答")
            if ans:
                icon = "✅" if user == ans else "❌"
                base = f"{icon}  你的答案: {user or '未作答'}    ✓ 正确答案: {ans}\n"
            else:
                base = ""
            analysis = q.get("analysis", "")
            lbl.configure(
                text=base + (f"💡 解析: {analysis}" if analysis else ""),
                text_color=("#10B981", "#34D399")
                if user == ans else
                (("#EF4444", "#FCA5A5") if ans else ("gray40", "gray60")),
            )
        # Top-of-card score
        self.status_lbl.configure(
            text=f"✅ 提交完成 — 正确 {correct} / {total}",
            text_color=("#10B981", "#34D399") if correct == total
            else (("#F59E0B", "#FBBF24") if correct >= total // 2
                  else ("#EF4444", "#F87171")),
        )
        self._submitted = True

    # =====================================================================
    # AI 高仿 (threading)
    # =====================================================================
    @safe_callback
    def _start_ai_similar(self) -> None:
        if self._ai_running:
            return
        if not self._items:
            self.status_lbl.configure(
                text="请先打开任意一篇阅读题,AI 才能以其为蓝本",
                text_color=("#F59E0B", "#FBBF24"),
            )
            return
        if not self.ai.has_api():
            from tkinter import messagebox
            messagebox.showwarning(
                "未配置 API",
                "请先在左下角点击「🔑 配置 API Key」配置大模型密钥。",
                parent=self.winfo_toplevel(),
            )
            return
        self._ai_running = True
        self.ai_btn.configure(state="disabled", text="⏳ AI 老师正在编写...")
        self.status_lbl.configure(
            text="⏳ AI 老师正在以当前真题为大纲,为你现场编写同题材高阶模拟题...",
            text_color=("#F59E0B", "#FBBF24"),
        )
        source = self._current_source or self._items[self._current_idx]
        ai = self.ai

        def worker():
            try:
                # L1: try LLM
                result = ai.generate_similar_reading_llm(source)
                # L2: fallback to template engine
                if result is None:
                    template_out = ai.generate_similar_reading(source)
                    # normalize to the new structure so render path
                    # doesn't need to special-case.
                    result = {
                        "title": template_out.get("title", "AI 仿写"),
                        "passage": template_out.get("passage", ""),
                        "questions": [
                            # Legacy template returns "1. B  2. C ..." in
                            # 'answers' but no full questions list, so
                            # we synthesise 5 minimal ones.
                            *self._minimal_questions_from_template(
                                source, template_out),
                        ],
                        "answers": template_out.get("answers", ""),
                        "analysis": template_out.get("analysis", ""),
                    }
                self.after(0, safe_callback(lambda r=result: self._on_ai_done(r)))
            except Exception:
                _log.exception("AI similar worker failed")
                self.after(0, safe_callback(self._on_ai_failed))

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _minimal_questions_from_template(source: dict, t: dict) -> list[dict]:
        """If the template engine returns only ``answers`` like
        '1. B 2. C ...', manufacture 5 placeholder Q items so the
        UI can still show 5 lines.
        """
        ans_text = t.get("answers", "")
        import re as _re
        letters = _re.findall(r"(\d+)\.\s*([A-D])", ans_text)
        out: list[dict] = []
        for i, (_, letter) in enumerate(letters[:5]):
            out.append({
                "q": f"Question {i + 1} (AI generated)",
                "options": ["(暂无选项 — 模板生成)", "—", "—", "—"],
                "answer": letter,
                "analysis": t.get("analysis", ""),
            })
        # Pad to 5
        while len(out) < 5:
            i = len(out)
            out.append({
                "q": f"Question {i + 1} (AI generated)",
                "options": ["(暂无选项 — 模板生成)", "—", "—", "—"],
                "answer": "A",
                "analysis": t.get("analysis", ""),
            })
        return out

    def _on_ai_done(self, result: dict) -> None:
        self._ai_running = False
        self.ai_btn.configure(state="normal",
                              text="✨ AI 生成相似阅读 (同题材同难度)")
        # Build a fake DB-row that the rest of the view can render
        ai_item = {
            "id": -1,  # virtual id
            "year": "AI",
            "session": "生成",
            "passage_title": result.get("title", "AI 仿写"),
            "passage": result.get("passage", ""),
            "questions": json.dumps(result.get("questions") or [],
                                    ensure_ascii=False),
            "options": json.dumps(result.get("questions") or [],
                                    ensure_ascii=False),
            "answers": result.get("answers", ""),
            "analysis": result.get("analysis", ""),
            "topic_type": "(AI 仿写)",
        }
        self._ai_extras.append(ai_item)
        self._current_idx = len(self._items)  # jump to the new one
        # append-and-render
        self._items = self._items + [ai_item]
        self._current_idx = len(self._items) - 1
        self.status_lbl.configure(
            text=f"✅ AI 已生成新题,已附加到末尾。当前共 {len(self._items)} 题",
            text_color=("#10B981", "#34D399"),
        )
        self._render_current()

    def _on_ai_failed(self) -> None:
        self._ai_running = False
        self.ai_btn.configure(state="normal",
                              text="✨ AI 生成相似阅读 (同题材同难度)")
        self.status_lbl.configure(
            text="❌ AI 生成失败,请检查 API Key 或网络",
            text_color=("#EF4444", "#F87171"),
        )


import re  # noqa: E402  -- at module scope, used by the regex above