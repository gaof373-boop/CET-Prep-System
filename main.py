"""Entry point for the CET Prep System.

Run with:
    python -X utf8 main.py
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

# Force UTF-8 stdout/stderr on Windows (avoids mojibake for Chinese output)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

# Make sure we can import local modules
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    # ---- pre-Tk: configure CJK fonts before any window opens ------------
    try:
        from ui.fonts import configure_cjk_fonts
        chosen = configure_cjk_fonts()
        print(f"[main] CJK font configured: {chosen}")
    except Exception as e:
        print(f"[main] WARN: CJK font setup failed: {e}")
        traceback.print_exc()

    # ---- install the GUI safety net (excepthook + Tk patch) -------------
    try:
        from ui.safe import install_excepthook
        install_excepthook()
        print("[main] Global excepthook installed.")
    except Exception as e:
        print(f"[main] WARN: excepthook install failed: {e}")
        traceback.print_exc()

    # ---- bootstrap DB then launch ---------------------------------------
    try:
        from core.db_init import init_database
        print("[main] Initializing database…")
        init_database()
    except Exception as e:
        print(f"[main] FATAL: database init failed: {e}")
        traceback.print_exc()
        return 1

    try:
        from ui.app import App
        print("[main] Starting UI…")
        app = App()
        # Apply CJK font AGAIN now that CTk has its own root. This is
        # cheap; configure_cjk_fonts() is idempotent.
        try:
            configure_cjk_fonts(master=app)
        except Exception:
            pass
        app.mainloop()
    except Exception as e:
        print(f"[main] FATAL: UI crashed: {e}")
        traceback.print_exc()
        # Keep the window alive on crash so the user can read the log.
        try:
            import tkinter as tk
            from tkinter import messagebox
            messagebox.showerror("程序崩溃",
                                 f"程序异常退出,详情已写入 logs/ui.log\n\n{e}")
        except Exception:
            pass
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
