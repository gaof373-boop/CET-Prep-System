"""Theme management: day/night mode + accent color."""

from __future__ import annotations

import json
from pathlib import Path

import customtkinter as ctk

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"

THEMES = {
    "light": {
        "appearance": "light",
        "fg": "#F5F7FA",
        "card": "#FFFFFF",
        "border": "#E2E8F0",
        "text": "#1A202C",
        "subtext": "#4A5568",
        "accent": "#3B82F6",
        "accent_hover": "#2563EB",
        "success": "#10B981",
        "warning": "#F59E0B",
        "danger": "#EF4444",
    },
    "dark": {
        "appearance": "dark",
        "fg": "#1A202C",
        "card": "#2D3748",
        "border": "#4A5568",
        "text": "#F7FAFC",
        "subtext": "#CBD5E0",
        "accent": "#60A5FA",
        "accent_hover": "#3B82F6",
        "success": "#34D399",
        "warning": "#FBBF24",
        "danger": "#F87171",
    },
}

LEVEL_COLORS = {
    "CET4": "#3B82F6",  # blue
    "CET6": "#8B5CF6",  # purple
}

SECTION_ICONS = {
    "vocabulary": "📝",
    "writing": "✍️",
    "reading": "📖",
    "listening": "🎧",
    "translation": "🗣️",
}


class ThemeManager:
    """Reads / writes the user's theme preference and exposes color tokens."""

    def __init__(self) -> None:
        self.config: dict = {}
        if CONFIG_PATH.exists():
            try:
                self.config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            except Exception:
                self.config = {}
        self.mode = self.config.get("theme", "light")
        if self.mode not in THEMES:
            self.mode = "light"

    @property
    def colors(self) -> dict[str, str]:
        return THEMES[self.mode]

    def toggle(self) -> str:
        self.mode = "dark" if self.mode == "light" else "light"
        self._persist()
        ctk.set_appearance_mode(self.colors["appearance"])
        return self.mode

    def apply(self) -> None:
        ctk.set_appearance_mode(self.colors["appearance"])
        ctk.set_default_color_theme("blue")

    def _persist(self) -> None:
        self.config["theme"] = self.mode
        CONFIG_PATH.write_text(
            json.dumps(self.config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
