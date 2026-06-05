"""🗣️ 翻译板块 — 逐句精批版。

布局:
    ┌────────────────┬───────────────────────────┐
    │ 📥 中文原文     │ ✍️ 你的作答 (大 Textbox)  │
    │ + 标准参考译文  │ [🤖 提交 AI 逐句精批]    │
    │ (左,可滚动)    │ (右,自由编辑)            │
    └────────────────┴───────────────────────────┘
                        ▼
    ┌─────────────────────────────────────────────┐
    │ 📊 逐句精批报告(markdown,可滚动)        │
    │ · 采分点遗漏   · 中式英语硬伤   · 替换建议 │
    │ · 润色版     · 总评                            │
    └─────────────────────────────────────────────┘
"""

from __future__ import annotations

import logging
import re
import threading
from tkinter import StringVar, Text
from typing import Any

import customtkinter as ctk

from core.ai_service import AIService
from core.data_manager import DataManager
from ui.fonts import ctk_font
from ui.safe import safe_callback, _logger as _log

_log = logging.getLogger("translation_view")


def _local_grade(chinese_text: str, reference: str, student: str) -> dict:
    """Offline heuristic fallback when LLM is unavailable.

    Computes a rough word-coverage score against the reference and
    surfaces 3 placeholder upgrade hints. Not a real grader.
    """
    ref_words = set(re.findall(r"[A-Za-z]+", reference.lower()))
    student_words = set(re.findall(r"[A-Za-z]+", student.lower()))
    if not ref_words:
        return {
            "missing_points": ["(本地评分) 参考译文为空"],
            "chinglish": [],
            "upgrades": [],
            "polished": student,
            "summary": "本地评分:无法比对,参考答案缺失。",
        }
    overlap = ref_words & student_words
    coverage = len(overlap) / len(ref_words)
    missing = sorted(ref_words - student_words)[:8]
    return {
        "missing_points": [f"漏译/未使用: {', '.join(missing)}"],
        "chinglish": [
            {"sentence": student[:60] + ("..." if len(student) > 60 else ""),
             "issue": "(本地) 无法逐句诊断,请配置 API Key 获得精确反馈。",
             "fix": "对比左侧标准译文,逐一对照语法与搭配。"}
        ] if student else [],
        "upgrades": [
            {"from": "very good", "to": "remarkable / outstanding",
             "reason": "四级常见词换高级表达。"},
        ] if coverage < 0.5 else [],
        "polished": student,
        "summary": f"(本地评分) 词覆盖 {coverage*100:.0f}% — 请配置 API Key 获得精确逐句诊断。",
    }


def _render_markdown_in_textbox(box: ctk.CTkTextbox, lines: list[tuple[str, str]]) -> None:
    """Insert (text, tag) pairs into the box, with simple tags:
        h  — heading (bold orange)
        ok — green text
        bad — red text
        hi — yellow highlight
        n  — normal
    Note: CTk textbox ``tag_config`` accepts only SINGLE color strings,
    not (light, dark) tuples, so we pick one set of colors that
    works in both themes.
    """
    box.configure(state="normal")
    box.delete("1.0", "end")
    box.tag_config("h",     foreground="#F59E0B")
    box.tag_config("ok",    foreground="#10B981")
    box.tag_config("bad",   foreground="#EF4444")
    box.tag_config("hi",    foreground="#F59E0B")
    box.tag_config("muted", foreground="#6B7280")
    for text, tag in lines:
        if tag not in ("h", "ok", "bad", "hi", "muted"):
            tag = "n"
        box.insert("end", text + "\n", tag)
    box.configure(state="disabled")


class TranslationView(ctk.CTkFrame):
    SECTION_KEY = "translation"
    SECTION_TITLE = "🗣️  翻译板块"

    def __init__(self, master, dm: DataManager, ai: AIService, level_var: StringVar):
        super().__init__(master, fg_color="transparent")
        self.dm = dm
        self.ai = ai
        self.level_var = level_var
        self._items: list[dict] = []
        self._current_idx: int = 0
        self._grading: bool = False
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
            header, text="🗣️  翻译板块",
            font=ctk_font(size=24, weight="bold"),
        ).pack(side="left")
        ctk.CTkLabel(
            header, text="  ·  逐句精批 · 中英对照 · AI 润色",
            font=ctk_font(size=12),
            text_color=("gray40", "gray60"),
        ).pack(side="left", padx=8)

        # status
        self.status_lbl = ctk.CTkLabel(
            self, text="", font=ctk_font(size=12),
            text_color=("gray40", "gray60"), anchor="w",
        )
        self.status_lbl.pack(fill="x", padx=24, pady=(0, 2))

        # nav strip (上一题 / 下一题 / 题目指示)
        nav = ctk.CTkFrame(self, fg_color="transparent")
        nav.pack(fill="x", padx=24, pady=(0, 6))
        ctk.CTkButton(
            nav, text="◀ 上一题", height=30, width=100,
            font=ctk_font(size=12),
            command=safe_callback(self._prev_item),
            fg_color=("#E2E8F0", "#1F2937"),
            text_color=("gray10", "gray90"),
            hover_color=("#CBD5E0", "#334155"),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            nav, text="下一题 ▶", height=30, width=100,
            font=ctk_font(size=12),
            command=safe_callback(self._next_item),
            fg_color=("#E2E8F0", "#1F2937"),
            text_color=("gray10", "gray90"),
            hover_color=("#CBD5E0", "#334155"),
        ).pack(side="left", padx=2)
        self.nav_lbl = ctk.CTkLabel(
            nav, text="—", font=ctk_font(size=12),
            text_color=("gray40", "gray60"),
        )
        self.nav_lbl.pack(side="left", padx=8)

        # upper body: two-column
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=(0, 6))
        body.grid_columnconfigure(0, weight=1, uniform="tr")
        body.grid_columnconfigure(1, weight=1, uniform="tr")
        body.grid_rowconfigure(0, weight=1)

        # ----- LEFT: Chinese + reference (read-only) -----
        self.left = ctk.CTkFrame(
            body, corner_radius=10,
            fg_color=("white", "#1F2937"), border_width=1,
        )
        self.left.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=0)
        ctk.CTkLabel(
            self.left, text="📥  中文原文  /  参考译文",
            font=ctk_font(size=14, weight="bold"), anchor="w",
        ).pack(fill="x", padx=14, pady=(10, 2))
        self.left_box = ctk.CTkTextbox(
            self.left, wrap="word", font=ctk_font(size=14),
        )
        self.left_box.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        # ----- RIGHT: student editor + submit -----
        self.right = ctk.CTkFrame(
            body, corner_radius=10,
            fg_color=("white", "#1F2937"), border_width=1,
        )
        self.right.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=0)
        ctk.CTkLabel(
            self.right, text="✍️  你的作答 (支持换行)",
            font=ctk_font(size=14, weight="bold"), anchor="w",
        ).pack(fill="x", padx=14, pady=(10, 2))
        self.editor = ctk.CTkTextbox(
            self.right, wrap="word", font=ctk_font(size=14),
            border_width=0,
        )
        self.editor.pack(fill="both", expand=True, padx=14, pady=(0, 6))
        ctk.CTkButton(
            self.right, text="🤖 提交 AI 逐句精批",
            height=40, font=ctk_font(size=13, weight="bold"),
            command=safe_callback(self._start_grading),
            fg_color=("#3B82F6", "#2563EB"),
            hover_color=("#2563EB", "#3B82F6"),
        ).pack(fill="x", padx=14, pady=(0, 10))

        # ----- Bottom: report panel (markdown-styled) -----
        report_frame = ctk.CTkFrame(
            self, corner_radius=10,
            fg_color=("white", "#1F2937"), border_width=1,
        )
        report_frame.pack(fill="both", expand=True, padx=24, pady=(0, 16))
        ctk.CTkLabel(
            report_frame, text="📊  逐句精批报告",
            font=ctk_font(size=14, weight="bold"), anchor="w",
        ).pack(fill="x", padx=14, pady=(10, 2))
        self.report_box = ctk.CTkTextbox(
            report_frame, wrap="word", font=ctk_font(size=12),
        )
        self.report_box.pack(fill="both", expand=True, padx=14, pady=(0, 10))
        self._render_report_empty()

    def _render_report_empty(self) -> None:
        _render_markdown_in_textbox(self.report_box, [
            ("(尚无报告)", "h"),
            ("", "n"),
            ("1. 在右侧编辑区输入你的翻译 (中→英)", "muted"),
            ("2. 点击「🤖 提交 AI 逐句精批」", "muted"),
            ("3. AI 会以左侧标准参考译文为基准,生成:", "muted"),
            ("   · 采分点遗漏(漏译的关键词)", "hi"),
            ("   · 中式英语硬伤(语法/搭配错误)", "bad"),
            ("   · 高级替换建议(把低级表达升级)", "ok"),
            ("   · 润色版完整参考译文", "ok"),
            ("   · 整体一句话总评", "h"),
        ])

    # =====================================================================
    # Refresh / nav
    # =====================================================================
    def refresh(self) -> None:
        try:
            level = self.level_var.get().replace("-", "")
            self._items = self.dm.list_translation(level)
            if not self._items:
                self._render_empty()
                return
            if self._current_idx >= len(self._items):
                self._current_idx = 0
            self._render_current()
        except Exception:
            _log.exception("TranslationView.refresh failed")
            self._render_empty()

    def _render_empty(self) -> None:
        self.left_box.configure(state="normal")
        self.left_box.delete("1.0", "end")
        self.left_box.insert("1.0", "(当前级别暂无翻译题)")
        self.left_box.configure(state="disabled")
        self.editor.configure(state="normal")
        self.editor.delete("1.0", "end")
        self.editor.configure(state="disabled")
        self.nav_lbl.configure(text="0 / 0")

    def _render_current(self) -> None:
        item = self._items[self._current_idx]
        zh = item.get("chinese_text", "")
        en = item.get("english_reference", "")
        year = item.get("year", "?")
        session = item.get("session", "")
        # left pane: Chinese + reference
        self.left_box.configure(state="normal")
        self.left_box.delete("1.0", "end")
        # single-color tags (CTk textbox doesn't support tuples)
        self.left_box.tag_config("h_tag", foreground="#3B82F6")
        self.left_box.tag_config("meta_tag", foreground="#6B7280")
        self.left_box.tag_config("zh_tag", foreground="#1E3A8A")
        self.left_box.tag_config("en_tag", foreground="#10B981")
        self.left_box.insert("end", f"📥  中文原文\n", "h_tag")
        self.left_box.insert(
            "end", f"   {year} {session}\n\n", "meta_tag")
        self.left_box.insert("end", f"{zh}\n\n", "zh_tag")
        self.left_box.insert("end", "📤  参考译文\n", "h_tag")
        self.left_box.insert("end", f"{en}", "en_tag")
        self.left_box.configure(state="disabled")
        # editor: clear
        self.editor.configure(state="normal")
        self.editor.delete("1.0", "end")
        self.editor.configure(state="normal")  # keep editable
        # nav
        self.nav_lbl.configure(
            text=f"第 {self._current_idx + 1}/{len(self._items)} 题"
        )
        # report: reset
        self._render_report_empty()
        self.status_lbl.configure(text="")

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

    # =====================================================================
    # Grading (threading)
    # =====================================================================
    @safe_callback
    def _start_grading(self) -> None:
        if self._grading or not self._items:
            return
        item = self._items[self._current_idx]
        student = self.editor.get("1.0", "end").strip()
        if not student or len(student) < 10:
            from tkinter import messagebox
            messagebox.showwarning("作答太短",
                                   "请先在右侧输入至少 10 个字符的翻译。",
                                   parent=self.winfo_toplevel())
            return
        if not self.ai.has_api():
            self._status("未配置 API Key,使用本地启发式评分", "#F59E0B")
            # immediate local grade
            self._render_report(_local_grade(
                item.get("chinese_text", ""),
                item.get("english_reference", ""),
                student,
            ))
            return
        self._grading = True
        self.status_lbl.configure(
            text="⏳ AI 老师正在逐句精批中,请稍候...",
            text_color=("#F59E0B", "#FBBF24"),
        )
        # render placeholder
        _render_markdown_in_textbox(self.report_box, [
            ("⏳  逐句精批中,AI 老师正在对比你的译文与标准参考译文...", "h"),
        ])
        zh = item.get("chinese_text", "")
        ref = item.get("english_reference", "")
        ai = self.ai
        s = student

        def worker():
            try:
                result = ai.grade_translation_line_by_line(zh, ref, s)
                if result is None:
                    result = _local_grade(zh, ref, s)
                self.after(0, safe_callback(lambda r=result: self._on_grade_done(r)))
            except Exception:
                _log.exception("translation grading worker failed")
                self.after(0, safe_callback(self._on_grade_failed))

        threading.Thread(target=worker, daemon=True).start()

    def _on_grade_done(self, result: dict) -> None:
        self._grading = False
        self._render_report(result)
        self._status("✅ 批改完成,可对照解析订正", "#10B981")

    def _on_grade_failed(self) -> None:
        self._grading = False
        self._status("❌ 批改失败,请检查 API Key", "#EF4444")

    # =====================================================================
    # Report rendering
    # =====================================================================
    def _render_report(self, r: dict) -> None:
        lines: list[tuple[str, str]] = []
        # 1. overall summary
        summary = r.get("summary", "").strip()
        if summary:
            lines.append(("📝  总评", "h"))
            lines.append((summary, "n"))
            lines.append(("", "n"))
        # 2. missing points
        miss = r.get("missing_points") or []
        if miss:
            lines.append(("🔴  采分点遗漏 (漏译/未使用关键词)", "h"))
            for m in miss:
                lines.append((f"   · {m}", "bad"))
            lines.append(("", "n"))
        # 3. Chinglish errors
        chinglish = r.get("chinglish") or []
        if chinglish:
            lines.append(("⚠️  中式英语硬伤", "h"))
            for e in chinglish:
                if isinstance(e, dict):
                    lines.append((f"   原句: {e.get('sentence', '')}", "muted"))
                    lines.append((f"   问题: {e.get('issue', '')}", "bad"))
                    lines.append((f"   建议: {e.get('fix', '')}", "ok"))
                else:
                    lines.append((f"   · {e}", "bad"))
            lines.append(("", "n"))
        # 4. upgrade suggestions
        ups = r.get("upgrades") or []
        if ups:
            lines.append(("💎  高级替换建议", "h"))
            for u in ups:
                if isinstance(u, dict):
                    lines.append((f"   低级: {u.get('from', '')}", "bad"))
                    lines.append((f"   高级: {u.get('to', '')}", "hi"))
                    lines.append((f"   理由: {u.get('reason', '')}", "muted"))
                else:
                    lines.append((f"   · {u}", "hi"))
            lines.append(("", "n"))
        # 5. polished version
        polished = r.get("polished", "").strip()
        if polished:
            lines.append(("🌟  润色版 (满分参考译文)", "h"))
            lines.append((polished, "ok"))
        if not lines:
            lines = [("(报告为空)", "muted")]
        _render_markdown_in_textbox(self.report_box, lines)
        # Append the cross-module catch button
        self._render_catch_button()

    def _render_catch_button(self) -> None:
        """A red button at the very bottom of the report that opens the
        catch-word dialog, letting the user push one or more words from
        the current translation attempt into the wrong book.
        """
        # Skip rendering on the empty placeholder state
        if not hasattr(self, "report_box"):
            return
        spacer = ctk.CTkFrame(self.report_box, fg_color="transparent", height=10)
        spacer.pack(fill="x", pady=(8, 0))
        ctk_btn_frame = ctk.CTkFrame(self.report_box, fg_color="transparent")
        ctk_btn_frame.pack(fill="x", padx=10, pady=(2, 8))
        ctk.CTkButton(
            ctk_btn_frame,
            text="➕  将翻译错词一键捕捉至错题本",
            height=40, font=ctk_font(size=13, weight="bold"),
            fg_color=("#EF4444", "#B91C1C"),
            hover_color=("#B91C1C", "#EF4444"),
            command=safe_callback(self._open_catch_dialog),
        ).pack(fill="x")
        ctk.CTkLabel(
            ctk_btn_frame,
            text="💡  点击后在弹窗中输入本次翻译里你不会的词,可批量连加。\n"
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
            section="translation", level=level,
            on_after_save=safe_callback(self._after_catch),
        )

    @safe_callback
    def _after_catch(self) -> None:
        # 错题本更新,无需刷新本视图
        pass

    def _status(self, text: str, color: str) -> None:
        self.status_lbl.configure(
            text=text,
            text_color=(color, color),
        )