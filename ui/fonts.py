"""Font setup for CustomTkinter / Tkinter.

This module is deliberately conservative: only **English system font
names** are ever handed to Tk. On Windows 10/11, Tk automatically falls
back to a Chinese-capable font when the requested font is missing a CJK
glyph, so Chinese text still renders — but Tk never has to parse a
Chinese family name, which avoids a class of ``TclError`` exceptions
seen on some Windows configurations.

Exposed API:
    - :data:`CJK_FAMILY` (str) — the family name handed to every widget.
    - :func:`font`         — returns ``(family, size, weight)`` tuple.
    - :func:`ctk_font`     — backwards-compatible alias for ``font``.
    - :func:`configure_cjk_fonts` — picks the best available font.
"""

from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont

from ui.safe import _logger as _log

# ---------------------------------------------------------------------------
# Safe English-only font candidates.
#
# Important: every entry must be a font name that is GUARANTEED to exist
# on any modern Windows / macOS / Linux system, with NO spaces that could
# be mis-tokenised by Tk's font parser. The picker falls back to
# "TkDefaultFont" if none of these are found.
# ---------------------------------------------------------------------------
_CANDIDATES: tuple[str, ...] = (
    "Arial",          # Windows + macOS + most Linux via msttcorefonts
    "Helvetica",      # macOS / Linux
    "DejaVu Sans",    # Linux (most distros)
    "Segoe UI",       # Windows Vista+
    "Liberation Sans",# Linux (RHEL/Fedora)
    "Sans",           # Generic X11 / Tk fallback
    "TkDefaultFont",  # Always-present Tk internal
)

# Default CJK_FAMILY before configure_cjk_fonts() is called.
CJK_FAMILY: str = "Arial"


# ---------------------------------------------------------------------------
# Named Tk fonts we re-point to the chosen family.
# ---------------------------------------------------------------------------
_NAMED_TK_FONTS = (
    "TkDefaultFont", "TkTextFont", "TkMenuFont",
    "TkHeadingFont", "TkCaptionFont", "TkSmallCaptionFont",
    "TkIconFont", "TkTooltipFont", "TkFixedFont",
)


def _pick_safe_font(available: set[str]) -> str:
    for name in _CANDIDATES:
        if name in available:
            return name
    return "TkDefaultFont"


def configure_cjk_fonts(master: tk.Misc | None = None) -> str:
    """Pick a safe system font and rewire Tk's named fonts to use it.

    Safe to call multiple times. Writes ``logs/font_report.txt`` for
    diagnostics. Returns the chosen family name.
    """
    global CJK_FAMILY
    own_root = False
    if master is None:
        root = tk.Tk()
        root.withdraw()
        master = root
        own_root = True
    try:
        available = set(tkfont.families(master))
        chosen = _pick_safe_font(available)
        CJK_FAMILY = chosen
        _log.info(
            f"configure_cjk_fonts: using {chosen!r} "
            f"({len(available)} system fonts detected)"
        )

        # Reconfigure all named Tk fonts to the chosen family.
        for name in _NAMED_TK_FONTS:
            try:
                f = tkfont.nametofont(name, master)
                f.configure(family=chosen)
            except Exception:
                pass

        try:
            master.option_add("*Font", chosen)
        except Exception:
            pass

        try:
            report_path = (
                Path(__file__).resolve().parent.parent
                / "logs" / "font_report.txt"
            )
            report_path.parent.mkdir(parents=True, exist_ok=True)
            safe_found = [f for f in _CANDIDATES if f in available]
            report_path.write_text(
                f"Total system fonts: {len(available)}\n"
                f"Chosen CJK font: {chosen}\n"
                f"Safe candidates available: "
                f"{safe_found or '(none — Tk will fall back to TkDefaultFont)'}\n",
                encoding="utf-8",
            )
        except Exception:
            pass

        return chosen
    finally:
        if own_root:
            try:
                master.destroy()  # type: ignore[union-attr]
            except Exception:
                pass


# ---------------------------------------------------------------------------
# The only two public functions view code calls.
# Both return a 3-tuple — never a CTkFont object — so Tk's font parser
# never has to unpack anything.
# ---------------------------------------------------------------------------
def font(size: int = 13, weight: str = "normal", family: str | None = None) -> tuple:
    """Return a plain ``(family, size, weight)`` tuple.

    Always uses :data:`CJK_FAMILY` (a safe English font) unless an explicit
    ``family`` is provided. Use this in every CTk widget's ``font=`` kwarg.
    """
    return (family or CJK_FAMILY, size, weight)


def ctk_font(size: int = 13, weight: str = "normal", family: str | None = None) -> tuple:
    """Backwards-compatible alias for :func:`font`. Returns a tuple."""
    return font(size=size, weight=weight, family=family)
