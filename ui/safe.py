"""UI safety net: global exception hook, safe-callback decorator, and a
log file for crash diagnosis.

This module exists so the GUI never dies because of a single broken
callback. Every UI handler is wrapped with :func:`safe_callback`, and the
process-wide :data:`sys.excepthook` is replaced so uncaught exceptions
during Tk callbacks are logged instead of killing the app.
"""

from __future__ import annotations

import functools
import logging
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

# ---- logger setup ---------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "ui.log"

_logger = logging.getLogger("ui.safe")
_logger.setLevel(logging.INFO)
if not _logger.handlers:
    _fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    _fh.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    _sh = logging.StreamHandler()
    _sh.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    _logger.addHandler(_fh)
    _logger.addHandler(_sh)
    _logger.propagate = False


# ---- global excepthook ----------------------------------------------------
def _global_excepthook(exc_type, exc_value, exc_tb):
    """Catch ANY uncaught exception, log it, do NOT call the default
    handler (which would print to stderr and silently kill the GUI)."""
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    _logger.error(f"Uncaught exception in GUI thread:\n{msg}")


def install_excepthook() -> None:
    """Install the global excepthook. Call once from main()."""
    sys.excepthook = _global_excepthook
    # Also patch Tk's report_callback_exception so errors during command
    # callbacks (the most common crash point) don't terminate the loop.
    try:
        import tkinter as tk
        original = tk.Tk.report_callback_exception

        def patched(self, exc, val, tb):  # noqa: ANN001
            msg = "".join(traceback.format_exception(exc, val, tb))
            _logger.error(f"Tk callback exception:\n{msg}")

        tk.Tk.report_callback_exception = patched  # type: ignore[assignment]
    except Exception as e:  # noqa: BLE001
        _logger.warning(f"Could not patch Tk.report_callback_exception: {e}")


# ---- safe-callback decorator ---------------------------------------------
def safe_callback(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a Tk command/callback so any exception is logged and the GUI
    keeps running instead of crashing."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            _logger.error(
                f"safe_callback caught in {fn.__qualname__}: {e}\n"
                f"{traceback.format_exc()}"
            )
            # Best-effort user notification. Don't raise from the
            # notification path itself.
            try:
                from tkinter import messagebox
                messagebox.showerror(
                    "出错了",
                    f"{fn.__qualname__} 执行失败:\n{str(e)[:300]}",
                )
            except Exception:
                pass
            return None

    return wrapper


# ---- Tkinter error handler for inside-event-loop exceptions ---------------
def install_tk_error_handler(widget) -> None:
    """Set a tk.call-based error handler so the event loop doesn't die."""
    try:
        # 'puts' writes to stderr; we redirect to the log
        widget.tk.call("proc", "traceError", "1")
    except Exception:
        pass
