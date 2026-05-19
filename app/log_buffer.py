"""In-memory ring buffer of recent log records.

Installed once at app startup so the in-app "回報問題" (bug report)
feature can attach the last N log lines WITHOUT writing logs to disk or
leaking them anywhere. The buffer is process-local and bounded.

Scrubbing of PHI / credentials happens later in bug_report.scrub() —
this module only captures raw lines; it never transmits anything.
"""
from __future__ import annotations

import logging
from collections import deque
from typing import Deque

_MAX = 400  # plenty for a traceback + recent context, still tiny in RAM
_buffer: Deque[str] = deque(maxlen=_MAX)


class _RingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            _buffer.append(self.format(record))
        except Exception:
            pass  # logging must never raise into the app


_installed = False


def install() -> None:
    """Attach the ring handler to the root logger exactly once."""
    global _installed
    if _installed:
        return
    h = _RingHandler()
    h.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    h.setLevel(logging.INFO)
    root = logging.getLogger()
    if root.level > logging.INFO or root.level == logging.NOTSET:
        root.setLevel(logging.INFO)
    root.addHandler(h)
    _installed = True


def recent(limit: int = 80) -> list[str]:
    """Return the last `limit` captured log lines (oldest→newest)."""
    if limit <= 0:
        return []
    items = list(_buffer)
    return items[-limit:]


def record(line: str) -> None:
    """Push an explicit line (e.g. a client-side error the UI reports)."""
    if line:
        _buffer.append(str(line)[:2000])
