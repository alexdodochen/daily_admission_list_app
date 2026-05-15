"""Generic draft persistence — JSON files under <user_data>/drafts/<bucket>/.

Used by:
  * Card 1 排班 (bucket="sched") — saves the year/month/baseline/X state from
    schedule_gen.html so the user can pause + resume.
  * Card 2 Key 班 (bucket="keyin") — saves the parsed Excel + EDR config so a
    long key-in session can survive a browser refresh.

Single-user local app — no auth, no per-user namespace. Filenames are sanitised
to alphanumerics + dash/underscore so the user can't escape the bucket dir.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .. import config as appconfig


def _root() -> Path:
    """Drafts live next to config.json (so they survive .exe re-builds)."""
    return Path(appconfig.CONFIG_PATH).parent / "drafts"


def _bucket_dir(bucket: str) -> Path:
    safe = re.sub(r"[^a-z0-9_]", "", bucket.lower())
    if not safe:
        raise ValueError("bucket required")
    p = _root() / safe
    p.mkdir(parents=True, exist_ok=True)
    return p


_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_\-一-鿿]")


def _safe_name(name: str) -> str:
    """Strip path separators + special chars; keep CJK + alnum + - _."""
    s = _SAFE_NAME_RE.sub("_", (name or "").strip())[:80]
    return s or f"draft_{int(time.time())}"


def save(bucket: str, name: str, payload: dict) -> dict:
    """Write <bucket>/<safe_name>.json. Returns metadata."""
    safe = _safe_name(name)
    p = _bucket_dir(bucket) / f"{safe}.json"
    body = {
        "name": safe,
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "saved_at_epoch": int(time.time()),
        "payload": payload,
    }
    p.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"name": safe, "saved_at": body["saved_at"], "size": p.stat().st_size}


def list_drafts(bucket: str) -> list[dict]:
    """Return [{name, saved_at, size}, ...] sorted newest first."""
    out = []
    for p in _bucket_dir(bucket).glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            out.append({
                "name": p.stem,
                "saved_at": data.get("saved_at", ""),
                "saved_at_epoch": data.get("saved_at_epoch", 0),
                "size": p.stat().st_size,
            })
        except Exception:
            continue
    out.sort(key=lambda d: d.get("saved_at_epoch", 0), reverse=True)
    return out


def load(bucket: str, name: str) -> dict | None:
    """Return saved {name, saved_at, payload} or None if not found."""
    safe = _safe_name(name)
    p = _bucket_dir(bucket) / f"{safe}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def delete(bucket: str, name: str) -> bool:
    safe = _safe_name(name)
    p = _bucket_dir(bucket) / f"{safe}.json"
    if not p.exists():
        return False
    p.unlink()
    return True
