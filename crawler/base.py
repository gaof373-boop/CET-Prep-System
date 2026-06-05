"""BaseScraper: HTTP client with retry, rate-limit, and structured logging."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = PROJECT_ROOT / "logs" / "crawler.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

# Polite default user agent — identifies our app, follows GitHub/Wikimedia policy.
USER_AGENT = (
    "CET-Prep-System-Crawler/1.0 "
    "(+https://github.com/local/cet-prep; educational use)"
)


def get_logger(name: str = "crawler") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


log = get_logger()


@dataclass
class RawItem:
    """A normalized record produced by any source. ``source`` tags it as
    ``github``, ``wiktionary``, ``wikipedia``, or ``synthetic`` so the UI
    can label content provenance correctly.
    """

    source: str
    section: str   # vocabulary | reading | listening | translation | writing
    level: str     # CET4 | CET6 | shared
    payload: dict[str, Any] = field(default_factory=dict)


class BaseScraper:
    """Reusable HTTP client with retry + rate limiting."""

    def __init__(
        self,
        *,
        min_interval: float = 1.0,
        max_retries: int = 3,
        timeout: float = 15.0,
        offline: bool = False,
    ):
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.timeout = timeout
        self._last_call = 0.0
        self.offline = offline
        self.session = requests.Session() if (requests and not offline) else None
        if self.session:
            self.session.headers.update({
                "User-Agent": USER_AGENT,
                "Accept": "application/json, text/plain;q=0.9, */*;q=0.5",
            })

    # ---------- low-level ----------
    def get(self, url: str, *, params: dict | None = None,
            headers: dict | None = None) -> bytes | None:
        """GET with retry + backoff. Returns None on permanent failure."""
        if self.offline or self.session is None:
            log.warning(f"[offline] would GET {url}")
            return None
        attempt = 0
        last_err: Exception | None = None
        while attempt < self.max_retries:
            self._respect_rate_limit()
            try:
                resp = self.session.get(
                    url, params=params, headers=headers,
                    timeout=self.timeout,
                )
                if resp.status_code == 200:
                    return resp.content
                if resp.status_code in (429, 500, 502, 503, 504):
                    last_err = RuntimeError(f"HTTP {resp.status_code}")
                    log.warning(f"GET {url} → {resp.status_code}, retrying…")
                else:
                    log.error(f"GET {url} → {resp.status_code}, giving up.")
                    return None
            except Exception as e:  # noqa: BLE001
                last_err = e
                log.warning(f"GET {url} failed: {e}")
            attempt += 1
            self._sleep(2 ** attempt + random.random())
        log.error(f"GET {url} exhausted retries: {last_err}")
        return None

    def get_json(self, url: str, **kw) -> Any | None:
        raw = self.get(url, **kw)
        if raw is None:
            return None
        try:
            import json
            return json.loads(raw)
        except Exception as e:  # noqa: BLE001
            log.error(f"JSON parse error for {url}: {e}")
            return None

    def get_text(self, url: str, **kw) -> str | None:
        raw = self.get(url, **kw)
        if raw is None:
            return None
        try:
            return raw.decode("utf-8", errors="replace")
        except Exception:
            return None

    # ---------- helpers ----------
    def _respect_rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.min_interval:
            self._sleep(self.min_interval - elapsed)
        self._last_call = time.monotonic()

    @staticmethod
    def _sleep(seconds: float) -> None:
        time.sleep(max(0.0, seconds))

    def network_ok(self, test_url: str = "https://en.wikipedia.org") -> bool:
        """Quick connectivity check used by the orchestrator."""
        if self.offline or self.session is None:
            return False
        try:
            r = self.session.head(test_url, timeout=5, allow_redirects=True)
            return r.status_code < 500
        except Exception:
            return False
