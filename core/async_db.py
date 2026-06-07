"""Async DB layer for the CET Prep System.

A single background worker thread runs all sqlite3 queries off the UI
thread, then posts results back via a thread-safe queue. UI code uses
``AsyncDB.run(...)`` to submit a query and then drains the queue from
``root.after()`` — never from a Tk callback's return value.

Why threading (not aiosqlite):
  * Zero new dependencies (aiosqlite is NOT in requirements.txt).
  * ``sqlite3`` connections are thread-safe as long as we don't share
    one connection across threads. We open a fresh connection inside
    the worker for every task, matching ``DataManager._conn()``.
  * CTk's mainloop is synchronous; mixing asyncio into it requires
    ``run_coroutine_threadsafe`` plumbing that buys nothing here.

UI contract:
  * ``adb = AsyncDB(dm, on_result=lambda req_id, payload: ...)``
  * ``adb.submit("list_vocabulary", level="CET4", ...)`` returns a
    request id (int). Use this to ignore stale results if the user
    has changed filters since the query was sent.
  * ``adb.pump()`` must be called from ``root.after(50, adb.pump)`` —
    it dispatches all currently-finished results to the callback.
  * ``adb.shutdown()`` on app exit.
"""

from __future__ import annotations

import queue
import threading
import time
import traceback
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .data_manager import DataManager


@dataclass
class _Request:
    req_id: int
    method: str
    kwargs: dict[str, Any]


@dataclass
class _Result:
    req_id: int
    method: str
    ok: bool
    value: Any = None
    error: Optional[str] = None
    error_tb: Optional[str] = None
    submitted_at: float = 0.0
    finished_at: float = 0.0


class AsyncDB:
    """Thread-pool-of-one: a single worker keeps SQLite writes serialised
    and avoids any cross-thread connection sharing. One worker is enough
    for the data volumes this app handles (~few thousand rows)."""

    def __init__(
        self,
        dm: DataManager,
        on_result: Callable[[int, _Result], None],
    ) -> None:
        self._dm = dm
        self._on_result = on_result
        self._q_out: "queue.Queue[_Result]" = queue.Queue()
        self._q_in: "queue.Queue[_Request | None]" = queue.Queue()
        self._next_id = 1
        self._id_lock = threading.Lock()
        self._worker = threading.Thread(
            target=self._run, name="AsyncDB-worker", daemon=True
        )
        self._worker.start()

    # ----- public API -----
    def submit(self, method: str, **kwargs: Any) -> int:
        """Queue a DB call. Returns a request id used to match results."""
        with self._id_lock:
            req_id = self._next_id
            self._next_id += 1
        self._q_in.put(_Request(req_id=req_id, method=method, kwargs=kwargs))
        return req_id

    def pump(self) -> None:
        """Drain all finished results and dispatch to ``on_result`` on the
        CALLING thread (i.e. the Tk main thread). Safe to call repeatedly."""
        while True:
            try:
                res = self._q_out.get_nowait()
            except queue.Empty:
                return
            try:
                self._on_result(res.req_id, res)
            except Exception:
                # The UI callback itself raised; swallow so pump() can
                # keep draining the queue.
                traceback.print_exc()

    def shutdown(self, timeout: float = 1.0) -> None:
        """Stop the worker. Safe to call multiple times."""
        try:
            self._q_in.put_nowait(None)
        except Exception:
            pass
        self._worker.join(timeout=timeout)

    # ----- worker loop -----
    def _run(self) -> None:
        while True:
            req = self._q_in.get()
            if req is None:
                return
            t0 = time.monotonic()
            try:
                fn = getattr(self._dm, req.method)
                value = fn(**req.kwargs)
                self._q_out.put(_Result(
                    req_id=req.req_id, method=req.method, ok=True,
                    value=value,
                    submitted_at=t0, finished_at=time.monotonic(),
                ))
            except Exception as e:  # noqa: BLE001
                self._q_out.put(_Result(
                    req_id=req.req_id, method=req.method, ok=False,
                    error=f"{type(e).__name__}: {e}",
                    error_tb=traceback.format_exc(),
                    submitted_at=t0, finished_at=time.monotonic(),
                ))
