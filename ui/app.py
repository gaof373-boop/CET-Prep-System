"""Main application window.

Layout:

    ┌─────────────────┬──────────────────────────────┐
    │  Sidebar (200)  │                              │
    │  - Brand        │                              │
    │  - 大级别按钮    │                              │
    │    · CET-4      │                              │
    │    · CET-6      │      Active Section View    │
    │  - 5 大板块按钮  │                              │
    │    · 📝 词汇板块 │                              │
    │    · ✍️ 写作板块 │                              │
    │    · 📖 阅读板块 │                              │
    │    · 🎧 听力板块 │                              │
    │    · 🗣️ 翻译板块 │                              │
    │  - API cfg      │                              │
    └─────────────────┴──────────────────────────────┘

All callbacks are wrapped with :func:`ui.safe.safe_callback` so a bug in
one view never kills the whole app.
"""

from __future__ import annotations

import customtkinter as ctk
from tkinter import StringVar
from typing import Any, Callable

from core.data_manager import DataManager
from core.ai_service import AIService
from core.theme_manager import ThemeManager, LEVEL_COLORS
from ui.components import SectionButton, LevelZoneButton, AppBrand
from ui.fonts import ctk_font
from ui.safe import safe_callback
from ui.views.dashboard import DashboardView
from ui.views.vocabulary import VocabularyView
from ui.views.writing import WritingView
from ui.views.reading import ReadingView
from ui.views.listening import ListeningView
from ui.views.translation import TranslationView
from ui.views.quiz import QuizView
from ui.views.wrong_book import WrongBookView


# Section definitions. The label includes the icon and the "板块" suffix
# as required by the spec. The first entry is the V2.0 home dashboard.
SECTIONS = [
    ("dashboard",  "📊  学霸看板"),
    ("vocabulary", "📝  词汇板块"),
    ("quiz",       "🎲  背单词自测"),
    ("wrongbook",  "🟥  错题本"),
    ("writing",    "✍️  写作板块"),
    ("reading",    "📖  阅读板块"),
    ("listening",  "🎧  听力板块"),
    ("translation", "🗣️  翻译板块"),
]

# Two big level-zone buttons
LEVEL_ZONES = [
    ("CET-4", "四级专区", LEVEL_COLORS["CET4"]),  # blue
    ("CET-6", "六级专区", LEVEL_COLORS["CET6"]),  # purple
]


def _safe_method(method: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap an unbound method so it survives exceptions during a Tk callback."""
    @safe_callback
    def wrapper(self, *args, **kwargs):  # noqa: ANN001
        return method(self, *args, **kwargs)
    return wrapper


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("CET 智胜 · 英语四六级备考系统")
        self.geometry("1280x800")
        self.minsize(1100, 720)
        # --- DPI safety: tell Tk the real pixel ratio and keep CTk at 1.0
        # so 200px really means 200px on 125%/150%/200% scaled screens.
        try:
            import platform
            if platform.system() == "Windows":
                from ctypes import windll
                try:
                    windll.shcore.SetProcessDpiAwareness(1)
                except Exception:
                    try:
                        windll.user32.SetProcessDPIAware()
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            ctk.set_window_scaling(1.0)
            ctk.set_widget_scaling(1.0)
        except Exception:
            pass

        # ---- state ----
        self.theme = ThemeManager()
        self.theme.apply()
        self.dm = DataManager()
        self.ai = AIService()
        self.level_var = StringVar(value="CET-4")
        self.current_section = "vocabulary"

        # ---- build UI ----
        try:
            self._build_layout()
        except Exception as e:
            from ui.safe import _logger
            _logger.exception(f"_build_layout failed: {e}")
            raise

        # Show the initial view
        try:
            self._show_section("dashboard")
        except Exception as e:
            from ui.safe import _logger
            _logger.exception(f"_show_section initial failed: {e}")
            try:
                self._show_section("vocabulary")
            except Exception:
                pass

    # ---------- layout ----------
    def _build_layout(self) -> None:
        # --- 2-column grid: sidebar (locked 200px) | main (elastic) ---
        # IRON RULE #1: column 0 must NEVER shrink below 200px
        #   weight=0  -> it will not consume extra horizontal space
        #   minsize=200 -> Tk WILL NOT let any DPI / scaling / sizefrom
        #                  manager crush it below 200 pixels
        self.grid_columnconfigure(0, weight=0, minsize=200, pad=0)
        # IRON RULE #2: column 1 absorbs ALL the leftover space
        self.grid_columnconfigure(1, weight=1, pad=0)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main()

    def _build_sidebar(self) -> None:
        # The frame is 200 logical pixels wide and is FORBIDDEN to shrink.
        # We pin it to the left wall ("nsw") so it never floats inward.
        self.sidebar = ctk.CTkFrame(
            self, width=200, corner_radius=0,
            fg_color=("#F8FAFC", "#0F172A"),
        )
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        # grid_propagate(False) means children are clipped to 200px
        # AND the frame refuses to resize itself based on children.
        self.sidebar.grid_propagate(False)
        # Force the internal Tk width to 200 right now, in case some
        # DPI rounding made the initial grid placement slightly narrower.
        self.sidebar.configure(width=200)
        # Lock the sidebar's own grid columns so its children can fill "ew"
        self.sidebar.grid_columnconfigure(0, weight=1, minsize=200, pad=0)

        # ---- brand ----
        AppBrand(self.sidebar,
                 on_toggle_theme=safe_callback(self._toggle_theme)).pack(
            fill="x", padx=0, pady=0)

        # ---- big level-zone buttons (CET-4 / CET-6) ----
        zt_label = ctk.CTkLabel(
            self.sidebar, text="📚  考试级别",
            font=ctk_font(size=12, weight="bold"),
            text_color=("gray40", "gray60"),
        )
        zt_label.pack(anchor="w", padx=14, pady=(0, 4))

        self.zone_buttons: dict[str, LevelZoneButton] = {}
        for level_key, sub_label, accent in LEVEL_ZONES:
            # Short two-line title to fit a 200px sidebar.
            # Top line: icon + Chinese zone name
            # Bottom line: small grey sub-label
            title = "📕  四级专区" if level_key == "CET-4" else "📘  六级专区"
            inner_sub = f"{level_key}  ·  {sub_label}"
            btn = LevelZoneButton(
                self.sidebar,
                label=title,
                sub_label=inner_sub,
                accent=accent,
                command=safe_callback(self._build_zone_callback(level_key)),
            )
            btn.pack(fill="x", padx=8, pady=3)
            self.zone_buttons[level_key] = btn

        # divider
        ctk.CTkFrame(self.sidebar, height=1, fg_color=("gray80", "gray30")).pack(
            fill="x", padx=16, pady=(6, 4))

        # ---- 5 section buttons ----
        sec_label = ctk.CTkLabel(
            self.sidebar, text="🧭  功能板块",
            font=ctk_font(size=12, weight="bold"),
            text_color=("gray40", "gray60"),
        )
        sec_label.pack(anchor="w", padx=16, pady=(4, 4))

        self.section_buttons: dict[str, SectionButton] = {}
        for key, label in SECTIONS:
            btn = SectionButton(
                self.sidebar, label=label,
                command=safe_callback(self._build_section_callback(key)),
            )
            btn.pack(fill="x", padx=14, pady=3)
            self.section_buttons[key] = btn

        # ---- API config at the bottom ----
        # NB: sidebar mixes pack() and grid() — that's allowed by Tk
        # as long as the children that DON'T use grid are managed
        # independently. We give the spacer an empty pack() so it
        # doesn't get squished by the API button's side="bottom".
        spacer = ctk.CTkFrame(self.sidebar, fg_color="transparent", height=20)
        spacer.pack(fill="x", padx=0, pady=0)
        ctk.CTkButton(
            self.sidebar, text="🔑  配置 API Key",
            height=36, corner_radius=8,
            fg_color=("#E2E8F0", "#1E293B"),
            text_color=("#0F172A", "#F1F5F9"),
            hover_color=("#CBD5E0", "#334155"),
            border_width=1,
            border_color=("#CBD5E1", "#475569"),
            command=safe_callback(self._open_api_dialog),
        ).pack(fill="x", padx=16, pady=(0, 18), side="bottom")

        # After all widgets are built, mark the current zone + section
        # as active so the visual state is correct on first paint.
        self._refresh_zone_highlight()
        self._refresh_section_highlight()

        # --- Final DPI guard: re-assert sidebar width after Tk has
        # finished its first geometry pass. This catches the case where
        # the initial layout was computed before our configure(width=200)
        # took effect (some Windows DPI round-trips do this).
        try:
            self.update_idletasks()
            self.sidebar.configure(width=200)
            self.sidebar.update_idletasks()
        except Exception:
            pass

        # Bind a watchdog on the root: if anything (DPI change, theme
        # switch, system font rescaling) tries to crush the sidebar
        # below 200px, we force it back.
        def _guard_sidebar(_event: object = None) -> None:
            try:
                if self.sidebar.winfo_width() < 200:
                    self.sidebar.configure(width=200)
            except Exception:
                pass
        self.bind("<Configure>", _guard_sidebar, add="+")

    def _build_section_callback(self, key: str) -> Callable[[], None]:
        from ui.safe import _logger

        def callback(_arg: Any = None) -> None:
            _logger.info(f"板块按钮 click → switching to {key!r}")
            self._show_section(key)

        return callback

    def _build_zone_callback(self, level_key: str) -> Callable[[], None]:
        from ui.safe import _logger

        def callback(_arg: Any = None) -> None:
            _logger.info(f"大级别按钮 click → switching level to {level_key!r}")
            self._switch_level(level_key)

        return callback

    def _build_main(self) -> None:
        self.main = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray95", "#1A202C"))
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(0, weight=1)
        # container for active view
        self.view_container = ctk.CTkFrame(self.main, fg_color="transparent")
        self.view_container.grid(row=0, column=0, sticky="nsew")
        self.view_container.grid_columnconfigure(0, weight=1)
        self.view_container.grid_rowconfigure(0, weight=1)

        # build all views (lazy-instantiated)
        self.views: dict[str, ctk.CTkBaseClass] = {}
        self._build_views()

    def _build_views(self) -> None:
        # V2.0: dashboard is the home; it doesn't need ai
        self.views["dashboard"] = DashboardView(self.view_container, self.dm, self.level_var)
        self.views["vocabulary"] = VocabularyView(self.view_container, self.dm, self.level_var)
        self.views["quiz"] = QuizView(self.view_container, self.dm, self.level_var)
        self.views["wrongbook"] = WrongBookView(self.view_container, self.dm, self.level_var)
        self.views["writing"] = WritingView(self.view_container, self.dm, self.ai, self.level_var)
        self.views["reading"] = ReadingView(self.view_container, self.dm, self.ai, self.level_var)
        self.views["listening"] = ListeningView(self.view_container, self.dm, self.ai, self.level_var)
        self.views["translation"] = TranslationView(self.view_container, self.dm, self.ai, self.level_var)

    # ---------- section switching ----------
    @_safe_method
    def _show_section(self, key: str) -> None:
        self.current_section = key
        # Hide all
        for v in self.views.values():
            try:
                v.grid_forget()
            except Exception:
                pass
        # Highlight selected button
        self._refresh_section_highlight()
        # Show selected view
        view = self.views[key]
        view.grid(row=0, column=0, sticky="nsew")
        if hasattr(view, "refresh"):
            view.refresh()

    @_safe_method
    def _switch_level(self, level_key: str) -> None:
        """Switch between CET-4 and CET-6 (the two big level-zone buttons).

        Updates the StringVar that every view reads from, refreshes
        the active highlight on the zone buttons, and triggers a
        refresh of the *currently visible* view so the user sees the
        data swap immediately.
        """
        self.level_var.set(level_key)
        self._refresh_zone_highlight()
        # Refresh the current view to load the new level's data
        view = self.views[self.current_section]
        if hasattr(view, "refresh"):
            view.refresh()

    def _refresh_zone_highlight(self) -> None:
        """Update which level-zone button is highlighted as active."""
        try:
            current = self.level_var.get()
            for key, btn in self.zone_buttons.items():
                btn.set_active(key == current)
        except Exception:
            from ui.safe import _logger
            _logger.exception("_refresh_zone_highlight failed")

    def _refresh_section_highlight(self) -> None:
        """Update which section button is highlighted as active."""
        try:
            level = self.level_var.get()
            accent = LEVEL_COLORS.get(level.replace("-", ""), "#3B82F6")
            for k, btn in self.section_buttons.items():
                btn.set_active(k == self.current_section, accent)
        except Exception:
            from ui.safe import _logger
            _logger.exception("_refresh_section_highlight failed")

    # ---------- legacy level switcher kept for compatibility ----------
    @_safe_method
    def _on_level_change(self, value: str) -> None:
        # Used by the (now removed) segmented button. The two big
        # CET-4 / CET-6 zone buttons call :meth:`_switch_level` directly.
        self._switch_level(value)

    # ---------- theme toggle ----------
    @_safe_method
    def _toggle_theme(self) -> None:
        new_mode = self.theme.toggle()
        # Re-render current view to apply new theme
        view = self.views[self.current_section]
        if hasattr(view, "refresh"):
            view.refresh()

    # ---------- API config dialog ----------
    @_safe_method
    def _open_api_dialog(self) -> None:
        from ui.components import info
        win = ctk.CTkToplevel(self)
        win.title("🔑  配置 AI API Key (可选)")
        win.geometry("540x360")
        win.grab_set()

        ctk.CTkLabel(win, text="配置 OpenAI 兼容接口",
                     font=ctk_font(size=16, weight="bold")).pack(
            anchor="w", padx=20, pady=(18, 4))
        ctk.CTkLabel(win, text="若不配置,系统将使用本地规则引擎生成拓展内容。",
                     font=ctk_font(size=12),
                     text_color=("gray40", "gray60")).pack(anchor="w", padx=20)

        ctk.CTkLabel(win, text="Base URL", anchor="w").pack(fill="x", padx=20, pady=(14, 2))
        base_entry = ctk.CTkEntry(win, width=500)
        base_entry.pack(padx=20)
        base_entry.insert(0, self.ai.config.get("base_url", "https://api.openai.com/v1"))

        ctk.CTkLabel(win, text="API Key", anchor="w").pack(fill="x", padx=20, pady=(10, 2))
        key_entry = ctk.CTkEntry(win, width=500, show="*")
        key_entry.pack(padx=20)
        key_entry.insert(0, self.ai.config.get("api_key", ""))

        ctk.CTkLabel(win, text="Model", anchor="w").pack(fill="x", padx=20, pady=(10, 2))
        model_entry = ctk.CTkEntry(win, width=500)
        model_entry.pack(padx=20)
        model_entry.insert(0, self.ai.config.get("model", "gpt-3.5-turbo"))

        @safe_callback
        def save():
            self.ai.config["base_url"] = base_entry.get().strip()
            self.ai.config["api_key"] = key_entry.get().strip()
            self.ai.config["model"] = model_entry.get().strip()
            self.ai.save_config()
            info(win, "已保存", "API 配置已保存。重新生成预测/拓展时会自动调用。")
            win.destroy()

        ctk.CTkButton(win, text="保存", command=save, height=36).pack(
            side="right", padx=20, pady=18)
        ctk.CTkButton(win, text="取消",
                      command=safe_callback(win.destroy), height=36,
                      fg_color=("gray70", "gray30"),
                      hover_color=("gray60", "gray40")).pack(
            side="right", pady=18)
