"""Cooperative cancellation registry for long-running operations.

Pattern: each long-running endpoint creates an `op_id` (typically
`step{N}_{date}`), records a flag at the start, polls `is_canceled(op_id)`
at safe checkpoints inside its loop, and clears the flag in a `finally`.
A separate `POST /api/op/cancel` endpoint sets the flag, and the running
op breaks out of its loop on the next check, returning partial results.

This is intentionally simpler than `asyncio.Task.cancel()`:
- No race with concurrent uvicorn workers (this app is single-user, single
  worker — module-global state is fine).
- Cooperative checkpoints make cleanup deterministic (we always close the
  Playwright browser, write back partial results, etc.).
- Cancellation never aborts a write that has already started in WEBCVIS /
  Google Sheets — it only stops the next iteration.
"""
from __future__ import annotations

import threading

_lock = threading.Lock()
_flags: dict[str, bool] = {}
_metadata: dict[str, dict] = {}


def start(op_id: str, meta: dict | None = None) -> None:
    """Register a new running operation. Clears any prior cancel flag for op_id."""
    with _lock:
        _flags[op_id] = False
        _metadata[op_id] = dict(meta or {})


def finish(op_id: str) -> None:
    """Clear all state for an operation that just ended (normal or canceled)."""
    with _lock:
        _flags.pop(op_id, None)
        _metadata.pop(op_id, None)


def request_cancel(op_id: str) -> bool:
    """Flag op_id for cancellation. Returns True if op was running."""
    with _lock:
        if op_id in _flags:
            _flags[op_id] = True
            return True
        return False


def is_canceled(op_id: str) -> bool:
    """Check whether op_id has been asked to cancel."""
    if not op_id:
        return False
    return _flags.get(op_id, False)


def list_running() -> list[str]:
    """For diagnostics — list currently-tracked op_ids."""
    with _lock:
        return [k for k, v in _flags.items() if not v]
