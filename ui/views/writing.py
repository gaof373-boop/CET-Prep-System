"""写作板块:三大子 Tab 完整闭环。

Tab 1  📚 历年真题      : 左列表 + 右详情,闪光词高亮
Tab 2  🔮 AI 押题预测   : threading 异步,押题 + 核心词 + 范文
Tab 3  ✍️ AI 智能批改   : 大输入框,提交后多线程批改(评分/纠错/替换/润色)
"""

from __future__ import annotations

import json
import logging
import re
import threading
from tkinter import StringVar, Text, END
from typing import Any

import customtkinter as ctk

from core.ai_service import AIService
from core.data_manager import DataManager
from ui.fonts import ctk_font
from ui.safe import safe_callback, _logger as _log

_log = logging.getLogger("writing_view")


# ---------------------------------------------------------------------------
# 闪光词 / 句型高亮配置
# ---------------------------------------------------------------------------
HIGHLIGHT_PHRASES: list[str] = [
    # 高分短语
    "moreover", "furthermore", "in addition", "what is more",
    "however", "nevertheless", "nonetheless", "on the contrary",
    "therefore", "consequently", "as a result", "accordingly",
    "in conclusion", "to sum up", "all in all",
    "from my perspective", "as far as I am concerned",
    "take ... into account", "play a vital role in",
    "it is high time that", "not only ... but also",
    "there is no denying that", "it goes without saying",
    # 高分句型骨架
    "sb. tend to", "be likely to", "be bound to", "ought to",
    "rather than", "instead of", "thanks to", "due to",
    "in terms of", "with regard to", "on the whole", "for the most part",
    "not merely ... but", "only if", "if only", "as long as",
    "the more ... the more", "no sooner ... than", "hardly ... when",
]
# Sorted longest-first so the highlighter prefers longer matches.
HIGHLIGHT_PHRASES = sorted(set(HIGHLIGHT_PHRASES), key=lambda s: -len(s))


def _make_tagged_text(essay: str) -> list[tuple[str, str]]:
    """Walk through ``essay`` and emit (text, tag) pairs.

    tag is one of:
        "h"        — a high-light phrase
        "n"        — normal text
    Used by ``_render_essay_with_highlights`` to apply different colors.
    """
    if not essay:
        return [("", "n")]
    # Build a single regex that matches any of the phrases (case-insensitive).
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(p) for p in HIGHLIGHT_PHRASES) + r")\b",
        re.IGNORECASE,
    )
    out: list[tuple[str, str]] = []
    pos = 0
    for m in pattern.finditer(essay):
        if m.start() > pos:
            out.append((essay[pos: m.start()], "n"))
        out.append((m.group(0), "h"))
        pos = m.end()
    if pos < len(essay):
        out.append((essay[pos:], "n"))
    return out


class WritingView(ctk.CTkFrame):
    SECTION_KEY = "writing"
    SECTION_TITLE = "✍️  写作板块"

    def __init__(self, master, dm: DataManager, ai: AIService, level_var: StringVar):
        super().__init__(master, fg_color="transparent")
        self.dm = dm
        self.ai = ai
        self.level_var = level_var
        # selection state for tab 1
        self._selected_writing_id: int | None = None
        # the currently displayed prediction (for grading context)
        self._current_topic: str = ""
        # build
        self._build()

    # =====================================================================
    # Layout
    # =====================================================================
    def _build(self) -> None:
        # header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(22, 6))
        ctk.CTkLabel(
            header, text="✍️  写作板块",
            font=ctk_font(size=24, weight="bold"),
        ).pack(side="left")
        self.level_hint = ctk.CTkLabel(
            header, text="",
            font=ctk_font(size=12),
            text_color=("#3B82F6", "#60A5FA"),
        )
        self.level_hint.pack(side="left", padx=12)

        # tabs
        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=24, pady=(6, 22))
        self.tabs.add("📚 历年真题")
        self.tabs.add("🔮 AI 押题预测")
        self.tabs.add("✍️ AI 智能批改")
        self._build_tab1(self.tabs.tab("📚 历年真题"))
        self._build_tab2(self.tabs.tab("🔮 AI 押题预测"))
        self._build_tab3(self.tabs.tab("✍️ AI 智能批改"))

    # =====================================================================
    # Tab 1 — 历年真题
    # =====================================================================
    def _build_tab1(self, parent) -> None:
        # split: left list | right detail
        paned = ctk.CTkFrame(parent, fg_color="transparent")
        paned.pack(fill="both", expand=True)
        paned.grid_columnconfigure(0, weight=1, minsize=240)
        paned.grid_columnconfigure(1, weight=3)
        paned.grid_rowconfigure(0, weight=1)

        # left list
        self.t1_left = ctk.CTkScrollableFrame(paned, label_text="真题列表")
        self.t1_left.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=4)

        # right detail
        self.t1_right = ctk.CTkScrollableFrame(paned, label_text="题目与范文")
        self.t1_right.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=4)

    def _render_tab1(self) -> None:
        try:
            for w in self.t1_left.winfo_children():
                w.destroy()
            for w in self.t1_right.winfo_children():
                w.destroy()
            level = self.level_var.get().replace("-", "")
            self.level_hint.configure(text=f"·  当前 {level}  ·  10 年真题 + 高分范文")
            papers = self.dm.list_writing(level)
            if not papers:
                ctk.CTkLabel(self.t1_left, text="(暂无该级别真题)",
                             text_color=("gray40", "gray60"), pady=20).pack()
                ctk.CTkLabel(self.t1_right, text="请切换到有真题的级别 (CET-4 / CET-6)",
                             text_color=("gray40", "gray60"), pady=40).pack()
                return
            for p in papers:
                self._build_paper_item(self.t1_left, p)
            # Auto-select first
            if papers and self._selected_writing_id is None:
                self._select_paper(papers[0]["id"])
        except Exception:
            _log.exception("_render_tab1 failed")

    def _build_paper_item(self, parent, p: dict) -> None:
        is_active = p["id"] == self._selected_writing_id
        # Active items get the brand background; inactive items stay
        # transparent (which means "use CTk's default surface"). We pass
        # a real (light, dark) tuple to fg_color and only set it when
        # active — otherwise the CTkButton will pick its theme default.
        if is_active:
            fg_color = ("#EFF6FF", "#1E3A8A")
            text_color = ("gray10", "gray90")
        else:
            fg_color = "transparent"
            text_color = ("gray10", "gray90")
        row = ctk.CTkButton(
            parent, corner_radius=8, height=60,
            fg_color=fg_color,
            hover_color=("#DBEAFE", "#1E3A8A"),
            text_color=text_color,
            anchor="w",
            command=safe_callback(lambda pid=p["id"]: self._select_paper(pid)),
            text=(
                f"📅 {p['year']} {p.get('session') or ''}\n"
                f"  {p.get('category') or ''}  ·  {p.get('topic') or '(无题目)'}"
            ),
        )
        row.pack(fill="x", padx=4, pady=4)

    def _select_paper(self, paper_id: int) -> None:
        self._selected_writing_id = paper_id
        # Re-render left (highlight) and right (detail)
        level = self.level_var.get().replace("-", "")
        paper = None
        for p in self.dm.list_writing(level):
            if p["id"] == paper_id:
                paper = p
                break
        if not paper:
            return
        # rebuild left list (to refresh highlight)
        try:
            for w in self.t1_left.winfo_children():
                w.destroy()
        except Exception:
            pass
        try:
            papers = self.dm.list_writing(level)
            for p in papers:
                self._build_paper_item(self.t1_left, p)
        except Exception:
            _log.exception("rebuild list failed")
        # render right detail
        self._render_paper_detail(paper)

    def _render_paper_detail(self, p: dict) -> None:
        try:
            for w in self.t1_right.winfo_children():
                w.destroy()
        except Exception:
            return
        # title
        ctk.CTkLabel(
            self.t1_right, text=f"📅 {p['year']} 年 {p.get('session') or ''}",
            font=ctk_font(size=18, weight="bold"), anchor="w",
        ).pack(fill="x", padx=14, pady=(12, 2))
        ctk.CTkLabel(
            self.t1_right, text=f"类别: {p.get('category') or '综合'}",
            font=ctk_font(size=12),
            text_color=("gray40", "gray60"),
        ).pack(fill="x", padx=14, pady=(0, 8))
        # requirements
        ctk.CTkLabel(self.t1_right, text="📝 题目要求",
                     font=ctk_font(size=14, weight="bold"), anchor="w"
                     ).pack(fill="x", padx=14, pady=(6, 2))
        ctk.CTkLabel(
            self.t1_right,
            text=p.get("requirements") or p.get("topic") or "(无题目)",
            font=ctk_font(size=13),
            text_color=("gray20", "gray80"),
            wraplength=720, justify="left", anchor="w",
        ).pack(fill="x", padx=14, pady=(0, 8))
        # sample essay
        if p.get("sample_essay"):
            ctk.CTkLabel(self.t1_right, text="📖 参考范文 (高亮 = 闪光短语)",
                         font=ctk_font(size=14, weight="bold"), anchor="w"
                         ).pack(fill="x", padx=14, pady=(6, 2))
            self._render_essay_with_highlights(self.t1_right, p["sample_essay"])
        if p.get("key_phrases"):
            ctk.CTkLabel(
                self.t1_right,
                text=f"🔑 关键词组:  {p['key_phrases']}",
                font=ctk_font(size=12),
                text_color=("#3B82F6", "#60A5FA"),
                wraplength=720, justify="left", anchor="w",
            ).pack(fill="x", padx=14, pady=(8, 14))

    def _render_essay_with_highlights(self, parent, essay: str) -> None:
        """Embed a text widget that pre-highlights all known high-value
        phrases in orange. The widget is read-only."""
        box = ctk.CTkTextbox(
            parent, height=280, wrap="word",
            font=ctk_font(size=13),
        )
        box.pack(fill="x", padx=14, pady=4)
        # CTkTextbox tag_config requires SINGLE color strings, not a
        # (light, dark) tuple — Tk applies the same color regardless of
        # theme. Use a single bright orange that reads well in both modes.
        box.tag_config("highlight", foreground="#F59E0B")
        box.configure(state="normal")
        for chunk, tag in _make_tagged_text(essay):
            if tag == "h":
                box.insert("end", chunk, "highlight")
            else:
                box.insert("end", chunk)
        box.configure(state="disabled")

    # =====================================================================
    # Tab 2 — AI 押题预测 (threading)
    # =====================================================================
    def _build_tab2(self, parent) -> None:
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(12, 8))
        ctk.CTkLabel(
            top, text="🔮 AI 2026 押题预测",
            font=ctk_font(size=18, weight="bold"),
        ).pack(side="left")
        ctk.CTkButton(
            top, text="🤖 立即押题 (调用大模型)",
            height=38, width=200,
            font=ctk_font(size=13, weight="bold"),
            fg_color=("#8B5CF6", "#7C3AED"),
            hover_color=("#7C3AED", "#8B5CF6"),
            command=safe_callback(self._start_prediction),
        ).pack(side="right", padx=4)

        # status / spinner
        self.t2_status = ctk.CTkLabel(
            parent, text="💡 点击「立即押题」开始 (调用 LLM 大约需要 5-15 秒)",
            font=ctk_font(size=12),
            text_color=("gray40", "gray60"),
        )
        self.t2_status.pack(fill="x", padx=14, pady=(0, 6))

        # content scroll
        self.t2_scroll = ctk.CTkScrollableFrame(parent, label_text="")
        self.t2_scroll.pack(fill="both", expand=True, padx=14, pady=(4, 14))

    def _render_tab2_empty(self) -> None:
        for w in self.t2_scroll.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self.t2_scroll,
            text="(尚未生成押题)  ·  点击右上「立即押题」按钮",
            text_color=("gray40", "gray60"),
            font=ctk_font(size=13),
            pady=40,
        ).pack()

    def _start_prediction(self) -> None:
        """Fire-and-forget: kick off a background thread that calls the
        LLM and pushes the result back to the UI via ``after(0, ...)``.
        Crucially, we do NOT block the main thread on the network call.
        """
        # Disable the button via a guard flag (cheap + safe)
        if getattr(self, "_predicting", False):
            return
        self._predicting = True
        self.t2_status.configure(
            text="⏳ AI 老师正在全力押题中, 请稍候...",
            text_color=("#F59E0B", "#FBBF24"),
        )
        # render a loading placeholder inside the scroll
        for w in self.t2_scroll.winfo_children():
            w.destroy()
        self.t2_progress = ctk.CTkLabel(
            self.t2_scroll,
            text="🌐 正在调用大模型...\n请耐心等待 5-15 秒",
            font=ctk_font(size=14),
            text_color=("#8B5CF6", "#A78BFA"),
            pady=60,
        )
        self.t2_progress.pack(pady=40)

        level = self.level_var.get().replace("-", "")
        ai = self.ai

        def worker():
            try:
                # The actual blocking call.
                out = ai.generate_writing_topic(level)
                # Marshal back to the Tk main thread.
                self.after(0, safe_callback(lambda o=out: self._on_prediction_done(o)))
            except Exception:
                _log.exception("prediction worker failed")
                self.after(
                    0,
                    safe_callback(lambda: self._on_prediction_failed()),
                )

        threading.Thread(target=worker, daemon=True).start()

    def _on_prediction_done(self, out: dict) -> None:
        self._predicting = False
        self.t2_status.configure(
            text="✅ 押题生成成功  ·  可以现在动笔或直接去「批改」Tab 润色",
            text_color=("#10B981", "#34D399"),
        )
        for w in self.t2_scroll.winfo_children():
            w.destroy()
        self._render_prediction(out)
        # Save current topic so tab 3 can pre-fill it
        self._current_topic = out.get("topic_zh", "")

    def _on_prediction_failed(self) -> None:
        self._predicting = False
        self.t2_status.configure(
            text="❌ 押题生成失败, 请检查 API Key 后重试",
            text_color=("#EF4444", "#F87171"),
        )
        for w in self.t2_scroll.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self.t2_scroll,
            text="(请确认左下角已配置 API Key,并能联网)",
            text_color=("gray40", "gray60"),
            font=ctk_font(size=12),
            pady=40,
        ).pack()

    def _render_prediction(self, out: dict) -> None:
        # topic — Chinese / English
        ctk.CTkLabel(
            self.t2_scroll, text="🎯 预测题目 (中)",
            font=ctk_font(size=14, weight="bold"),
        ).pack(anchor="w", padx=8, pady=(12, 2))
        ctk.CTkLabel(
            self.t2_scroll, text=out.get("topic_zh", "(无)"),
            font=ctk_font(size=16, weight="bold"),
            text_color=("#3B82F6", "#60A5FA"),
            wraplength=720, justify="left",
        ).pack(anchor="w", padx=8, pady=(0, 8))
        ctk.CTkLabel(
            self.t2_scroll, text="🎯 Prompt (English)",
            font=ctk_font(size=14, weight="bold"),
        ).pack(anchor="w", padx=8, pady=(4, 2))
        ctk.CTkLabel(
            self.t2_scroll, text=out.get("topic_en", "(no English prompt)"),
            font=ctk_font(size=14, weight="bold"),
            text_color=("#10B981", "#34D399"),
            wraplength=720, justify="left",
        ).pack(anchor="w", padx=8, pady=(0, 8))
        # key points
        ctk.CTkLabel(
            self.t2_scroll, text="🔑 核心词提示",
            font=ctk_font(size=14, weight="bold"),
        ).pack(anchor="w", padx=8, pady=(8, 2))
        ctk.CTkLabel(
            self.t2_scroll, text=f"中文: {out.get('key_points_zh', '(无)')}",
            font=ctk_font(size=12),
            text_color=("gray20", "gray80"),
            wraplength=720, justify="left",
        ).pack(anchor="w", padx=8)
        ctk.CTkLabel(
            self.t2_scroll, text=f"English: {out.get('key_points_en', '(none)')}",
            font=ctk_font(size=12),
            text_color=("gray20", "gray80"),
            wraplength=720, justify="left",
        ).pack(anchor="w", padx=8, pady=(0, 8))
        # sample essay (with highlights)
        ctk.CTkLabel(
            self.t2_scroll, text="✒️ 高分参考范文 (高亮 = 闪光短语)",
            font=ctk_font(size=14, weight="bold"),
        ).pack(anchor="w", padx=8, pady=(8, 2))
        self._render_essay_with_highlights(
            self.t2_scroll, out.get("essay_zh", "(无范文)"),
        )
        ctk.CTkLabel(self.t2_scroll, text=" ").pack(pady=8)

    # =====================================================================
    # Tab 3 — AI 智能批改 (threading)
    # =====================================================================
    def _build_tab3(self, parent) -> None:
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(12, 6))
        ctk.CTkLabel(
            top, text="✍️ AI 智能批改润色官",
            font=ctk_font(size=18, weight="bold"),
        ).pack(side="left")
        ctk.CTkButton(
            top, text="📋 套用押题题目",
            height=34, width=140,
            font=ctk_font(size=12),
            command=safe_callback(self._use_prediction_topic),
            fg_color=("#E2E8F0", "#2D3748"),
            text_color=("gray10", "gray90"),
            hover_color=("#CBD5E0", "#334155"),
        ).pack(side="right", padx=4)
        ctk.CTkButton(
            top, text="🗑 清空",
            height=34, width=80,
            font=ctk_font(size=12),
            command=safe_callback(self._clear_essay),
            fg_color=("#E2E8F0", "#2D3748"),
            text_color=("gray10", "gray90"),
            hover_color=("#CBD5E0", "#334155"),
        ).pack(side="right", padx=4)

        # topic field
        topic_row = ctk.CTkFrame(parent, fg_color="transparent")
        topic_row.pack(fill="x", padx=14, pady=(4, 6))
        ctk.CTkLabel(topic_row, text="📝 题目:",
                     font=ctk_font(size=12, weight="bold")).pack(side="left", padx=(0, 4))
        self.t3_topic_var = StringVar()
        ctk.CTkEntry(
            topic_row, textvariable=self.t3_topic_var,
            placeholder_text="(在这里输入或粘贴作文题目)",
            height=30, font=ctk_font(size=12),
        ).pack(side="left", fill="x", expand=True, padx=4)

        # Two-pane: left = editor + submit, right = report
        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=14, pady=(4, 12))
        body.grid_columnconfigure(0, weight=3, uniform="grade")
        body.grid_columnconfigure(1, weight=4, uniform="grade")
        body.grid_rowconfigure(0, weight=1)

        # left pane
        left = ctk.CTkFrame(body, corner_radius=10,
                            fg_color=("white", "#1F2937"), border_width=1)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=0)
        ctk.CTkLabel(left, text="✍️ 你的作文 (支持换行)",
                     font=ctk_font(size=12, weight="bold"), anchor="w"
                     ).pack(anchor="w", padx=10, pady=(8, 0))
        self.t3_editor = ctk.CTkTextbox(
            left, wrap="word", font=ctk_font(size=14),
            border_width=0,
        )
        self.t3_editor.pack(fill="both", expand=True, padx=10, pady=8)
        # submit
        ctk.CTkButton(
            left, text="🚀 提交 AI 批改",
            height=42, font=ctk_font(size=14, weight="bold"),
            fg_color=("#3B82F6", "#2563EB"),
            hover_color=("#2563EB", "#3B82F6"),
            command=safe_callback(self._start_grading),
        ).pack(fill="x", padx=10, pady=(0, 10))

        # right pane
        right = ctk.CTkScrollableFrame(body, label_text="📊 批改报告")
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=0)
        self.t3_report = right
        self._render_report_empty()

    def _render_report_empty(self) -> None:
        for w in self.t3_report.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self.t3_report,
            text="(尚无报告)\n\n提交作文后,这里会显示:\n"
                 "· 权威评分\n· 语法纠错\n· 高级词汇替换\n· 满分润色版",
            font=ctk_font(size=12),
            text_color=("gray40", "gray60"),
            pady=40,
        ).pack()

    def _use_prediction_topic(self) -> None:
        if self._current_topic:
            self.t3_topic_var.set(self._current_topic)
        else:
            self.t3_topic_var.set("")

    def _clear_essay(self) -> None:
        try:
            self.t3_editor.delete("1.0", "end")
        except Exception:
            pass

    def _start_grading(self) -> None:
        essay = self.t3_editor.get("1.0", "end").strip()
        if not essay or len(essay) < 20:
            from tkinter import messagebox
            messagebox.showwarning("作文太短", "请先在左侧输入至少 20 个字符的作文。",
                                   parent=self.winfo_toplevel())
            return
        if not self.ai.has_api():
            from tkinter import messagebox
            messagebox.showwarning("未配置 API",
                                   "请先在左下角点击「🔑 配置 API Key」配置大模型密钥。",
                                   parent=self.winfo_toplevel())
            return
        topic_zh = self.t3_topic_var.get().strip() or "通用英语作文"
        # render progress
        for w in self.t3_report.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self.t3_report,
            text="⏳ AI 老师正在批改...\n预计 5-15 秒",
            font=ctk_font(size=14, weight="bold"),
            text_color=("#F59E0B", "#FBBF24"),
            pady=80,
        ).pack()

        ai = self.ai
        essay_to_grade = essay
        topic_for_grade = topic_zh

        def worker():
            try:
                result = ai.grade_essay(topic_for_grade, essay_to_grade)
                if result is None:
                    # graceful fallback
                    result = self._local_grade(topic_for_grade, essay_to_grade)
                self.after(0, safe_callback(lambda r=result: self._on_grade_done(r)))
            except Exception:
                _log.exception("grading worker failed")
                self.after(0, safe_callback(lambda: self._on_grade_failed()))

        threading.Thread(target=worker, daemon=True).start()

    def _on_grade_done(self, result: dict) -> None:
        for w in self.t3_report.winfo_children():
            w.destroy()
        self._render_report(result)

    def _on_grade_failed(self) -> None:
        for w in self.t3_report.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self.t3_report,
            text="❌ 批改失败\n请检查网络 / API Key / 配额",
            font=ctk_font(size=14, weight="bold"),
            text_color=("#EF4444", "#F87171"),
            pady=80,
        ).pack()

    def _local_grade(self, topic_zh: str, essay: str) -> dict:
        """Offline fallback grading (when LLM is unavailable).

        Computes a rough score from length + an over-emphasis on
        high-value phrases. Not a real grader — just enough to give
        the user useful feedback when the API is down.
        """
        words = essay.split()
        n_words = len(words)
        # 0-15 score
        score = min(15, max(2, n_words // 12))
        # detect "highlights" count
        high_count = sum(
            1 for p in HIGHLIGHT_PHRASES
            if re.search(r"\b" + re.escape(p) + r"\b", essay, re.IGNORECASE)
        )
        return {
            "score": score,
            "summary": f"(离线本地评分) 词数 {n_words}, 检测到 {high_count} 个闪光短语。",
            "errors": [],
            "upgrades": [
                {
                    "from": "very / important / many / good",
                    "to": "significantly / vital / numerous / beneficial",
                    "reason": "四级常见词换高级,立刻升一档",
                }
            ] if high_count < 3 else [],
            "polished": f"[Offline mode] {essay}",
        }

    def _render_report(self, r: dict) -> None:
        # 1) 评分
        score = r.get("score", 0)
        score_color = (
            "#10B981" if score >= 12 else
            "#F59E0B" if score >= 8 else
            "#EF4444"
        )
        head = ctk.CTkFrame(self.t3_report, fg_color="transparent")
        head.pack(fill="x", padx=10, pady=(10, 6))
        ctk.CTkLabel(
            head, text=f"{score}",
            font=ctk_font(size=48, weight="bold"),
            text_color=(score_color, score_color),
        ).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            head, text=f"/ 15  分",
            font=ctk_font(size=18, weight="bold"),
            text_color=("gray40", "gray60"),
        ).pack(side="left", pady=(20, 0))
        ctk.CTkLabel(
            head, text=r.get("summary", ""),
            font=ctk_font(size=12),
            text_color=("gray20", "gray80"),
            wraplength=420, justify="left",
        ).pack(side="left", padx=12, pady=(20, 0), fill="x", expand=True)

        # 2) 语法纠错
        errors = r.get("errors") or []
        ctk.CTkLabel(
            self.t3_report, text="🔴 语法/拼写纠错",
            font=ctk_font(size=14, weight="bold"),
        ).pack(anchor="w", padx=10, pady=(10, 2))
        if not errors:
            ctk.CTkLabel(
                self.t3_report, text="✅ 未发现明显语法错误",
                font=ctk_font(size=12), text_color=("#10B981", "#34D399"),
            ).pack(anchor="w", padx=14, pady=(0, 6))
        else:
            for e in errors:
                self._render_error(self.t3_report, e)

        # 3) 高级替换
        upgrades = r.get("upgrades") or []
        ctk.CTkLabel(
            self.t3_report, text="💎 高级词汇/句型替换",
            font=ctk_font(size=14, weight="bold"),
        ).pack(anchor="w", padx=10, pady=(10, 2))
        if not upgrades:
            ctk.CTkLabel(
                self.t3_report, text="(暂无可替换项,继续保持高级表达!)",
                font=ctk_font(size=12),
                text_color=("gray40", "gray60"),
            ).pack(anchor="w", padx=14, pady=(0, 6))
        else:
            for u in upgrades:
                self._render_upgrade(self.t3_report, u)

        # 4) 满分润色
        ctk.CTkLabel(
            self.t3_report, text="🌟 终极润色版 (满分范文)",
            font=ctk_font(size=14, weight="bold"),
        ).pack(anchor="w", padx=10, pady=(10, 2))
        polished_box = ctk.CTkTextbox(
            self.t3_report, height=260, wrap="word",
            font=ctk_font(size=13),
        )
        polished_box.pack(fill="x", padx=10, pady=4)
        polished_box.configure(state="normal")
        for chunk, tag in _make_tagged_text(r.get("polished", "(AI 未返回润色版)")):
            if tag == "h":
                polished_box.insert("end", chunk, "highlight")
            else:
                polished_box.insert("end", chunk)
        polished_box.tag_config("highlight", foreground="#F59E0B")
        polished_box.configure(state="disabled")

        # 5) 跨板块错词捕捉按钮
        ctk.CTkLabel(
            self.t3_report, text=" ",
            font=ctk_font(size=4),
        ).pack(pady=(6, 0))
        ctk_btn_frame = ctk.CTkFrame(self.t3_report, fg_color="transparent")
        ctk_btn_frame.pack(fill="x", padx=10, pady=(2, 8))
        ctk.CTkButton(
            ctk_btn_frame,
            text="➕  将写译错词一键捕捉至错题本",
            height=40, font=ctk_font(size=13, weight="bold"),
            fg_color=("#EF4444", "#B91C1C"),
            hover_color=("#B91C1C", "#EF4444"),
            command=safe_callback(self._open_catch_dialog),
        ).pack(fill="x")
        ctk.CTkLabel(
            ctk_btn_frame,
            text="💡  点击后在弹窗中输入本次作文里你不会的词,可批量连加。\n"
                 "   词会自动出现在「词汇 -> 🟥 错题本」并接受「背单词自测」的高频抽测。",
            font=ctk_font(size=11),
            text_color=("gray40", "gray60"),
            justify="left", anchor="w", wraplength=480,
        ).pack(fill="x", pady=(4, 0))

    def _open_catch_dialog(self) -> None:
        from ui.views.catch_word import open_catch_dialog
        level = self.level_var.get().replace("-", "")
        open_catch_dialog(
            self.winfo_toplevel(),
            self.dm,
            section="writing", level=level,
            on_after_save=safe_callback(self._after_catch),
        )

    @safe_callback
    def _after_catch(self) -> None:
        # 错题本更新,无需刷新本视图;在用户切到错题本时会重读 DB
        pass

    def _render_error(self, parent, e: dict) -> None:
        box = ctk.CTkFrame(parent, corner_radius=8,
                            fg_color=("#FEF2F2", "#7F1D1D"),
                            border_width=1, border_color=("#FCA5A5", "#FCA5A5"))
        box.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(
            box, text=f"❌  原句: {e.get('snippet', '')}",
            font=ctk_font(size=12, weight="bold"),
            text_color=("#B91C1C", "#FECACA"),
            wraplength=420, justify="left", anchor="w",
        ).pack(anchor="w", padx=10, pady=(6, 0))
        ctk.CTkLabel(
            box, text=f"💡 问题: {e.get('issue', '')}",
            font=ctk_font(size=11),
            text_color=("gray20", "gray80"),
            wraplength=420, justify="left", anchor="w",
        ).pack(anchor="w", padx=10, pady=(0, 0))
        ctk.CTkLabel(
            box, text=f"✅ 修正: {e.get('fix', '')}",
            font=ctk_font(size=12, weight="bold"),
            text_color=("#10B981", "#34D399"),
            wraplength=420, justify="left", anchor="w",
        ).pack(anchor="w", padx=10, pady=(0, 6))

    def _render_upgrade(self, parent, u: dict) -> None:
        box = ctk.CTkFrame(parent, corner_radius=8,
                            fg_color=("#FFFBEB", "#78350F"),
                            border_width=1, border_color=("#FCD34D", "#FCD34D"))
        box.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(
            box, text=f"🔻 低级: {u.get('from', '')}",
            font=ctk_font(size=12),
            text_color=("#92400E", "#FDE68A"),
            wraplength=420, justify="left", anchor="w",
        ).pack(anchor="w", padx=10, pady=(6, 0))
        ctk.CTkLabel(
            box, text=f"🔺 高级: {u.get('to', '')}",
            font=ctk_font(size=12, weight="bold"),
            text_color=("#10B981", "#34D399"),
            wraplength=420, justify="left", anchor="w",
        ).pack(anchor="w", padx=10, pady=(0, 0))
        if u.get("reason"):
            ctk.CTkLabel(
                box, text=f"💬 {u['reason']}",
                font=ctk_font(size=11),
                text_color=("gray20", "gray80"),
                wraplength=420, justify="left", anchor="w",
            ).pack(anchor="w", padx=10, pady=(0, 6))

    # =====================================================================
    # Public refresh
    # =====================================================================
    @safe_callback
    def refresh(self) -> None:
        try:
            self._render_tab1()
            # tab 2 and 3 don't need a data refresh — they are interactive
        except Exception:
            _log.exception("WritingView.refresh failed")
            try:
                for w in self.t1_left.winfo_children():
                    w.destroy()
                for w in self.t1_right.winfo_children():
                    w.destroy()
                ctk.CTkLabel(
                    self.t1_left, text="⚠ 加载失败", pady=20,
                    text_color=("#EF4444", "#F87171"),
                ).pack()
            except Exception:
                pass