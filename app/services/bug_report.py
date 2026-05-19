"""In-app "回報問題" (bug report) builder.

The app handles PHI (chart numbers, patient names, EMR text) and lives in
a PUBLIC GitHub repo, so every diagnostic payload is hard-scrubbed before
it can leave the machine:

  * concrete credentials (the actual config values) are replaced by name
  * key/token/password `k=v` pairs are redacted
  * long digit runs (病歷號 / DOB-like) → [數字已隱藏]
  * api-key shaped blobs (sk-… / AIza… / 32+ char tokens) → [金鑰已隱藏]
  * emails → local part hidden
  * obvious "姓名: 王小明" patterns → name hidden

Two delivery paths (user picked both):
  - build_issue_url(): a prefilled GitHub *new issue* URL the user opens
    and reviews before submitting (public — user is the final PHI gate).
  - write_report_file(): a scrubbed .txt under DATA_DIR/bug_reports the
    user can send privately.

Nothing here makes a network call or auto-submits — the user always
acts explicitly.
"""
from __future__ import annotations

import platform
import re
import sys
import urllib.parse
from datetime import datetime
from pathlib import Path

from .. import config as appconfig
from .. import log_buffer
from . import updater

REPO = "alexdodochen/daily_admission_list_app"
_NEW_ISSUE = f"https://github.com/{REPO}/issues/new"

# GitHub caps a prefilled-issue URL well under browser limits; keep the
# body comfortably small and trim logs first if needed.
_MAX_BODY = 6500


# --------------------------- scrubbing ---------------------------

_RE_KV = re.compile(
    r"(?i)\b(token|password|passwd|pass|secret|api[_-]?key|authorization|bearer)"
    r"\s*[:=]\s*\S+")
_RE_SK = re.compile(r"\b(sk-[A-Za-z0-9_\-]{12,}|AIza[0-9A-Za-z_\-]{10,})")
_RE_LONGTOK = re.compile(r"\b[A-Za-z0-9_\-]{40,}\b")
_RE_DIGITS = re.compile(r"\b\d{6,12}\b")          # chart-no / DOB-ish
_RE_EMAIL = re.compile(r"\b[\w.+-]+@([\w-]+\.[\w.-]+)\b")
# Name context: a name label followed by a colon OR whitespace then a
# short CJK/alpha token. Whitespace separator is allowed deliberately —
# over-redacting nearby words in a diagnostic dump is the safe side; a
# leaked patient name is not.
_RE_NAME_CTX = re.compile(
    r"(?i)(姓名|病人|患者|name|patient)\s*[:：=]?\s*[一-鿿A-Za-z]{2,6}")


def _secret_values() -> list[str]:
    """Exact config values to blanket-redact wherever they appear."""
    cfg = appconfig.load()
    vals = [
        cfg.llm_api_key, cfg.cathlab_pass, cfg.cathlab_user,
        cfg.line_token, cfg.line_group_id, cfg.google_creds_path,
        cfg.sheet_id, cfg.schedule_sheet_id,
    ]
    return [v for v in vals if v and isinstance(v, str) and len(v) >= 4]


def scrub(text: str) -> str:
    if not text:
        return ""
    out = text
    for v in _secret_values():
        out = out.replace(v, "[已隱藏設定值]")
    out = _RE_KV.sub(lambda m: f"{m.group(1)}=[已隱藏]", out)
    out = _RE_SK.sub("[金鑰已隱藏]", out)
    out = _RE_LONGTOK.sub("[字串已隱藏]", out)
    out = _RE_NAME_CTX.sub(lambda m: f"{m.group(1)}: [姓名已隱藏]", out)
    out = _RE_DIGITS.sub("[數字已隱藏]", out)
    out = _RE_EMAIL.sub(r"[email已隱藏]@\1", out)
    return out


# --------------------------- collect ---------------------------

def _flags() -> dict:
    cfg = appconfig.load()
    try:
        from . import cathlab_service
        cath = cathlab_service.cathlab_static_status().get("present", False)
    except Exception:
        cath = False
    pw = ""
    try:
        import os
        base = getattr(sys, "_MEIPASS", None)
        if base:
            p = Path(base) / "ms-playwright"
            pw = "bundled" if p.is_dir() and any(
                d.name.startswith("chromium") for d in p.iterdir()) else "missing"
        else:
            pw = "dev"
    except Exception:
        pw = "unknown"
    return {
        "llm_provider": cfg.llm_provider or "(未設定)",
        "llm_key_set": bool(cfg.llm_api_key),
        "sheet_id_set": bool(cfg.sheet_id),
        "schedule_sheet_set": bool(cfg.schedule_sheet_id),
        "creds_found": appconfig.sa_status().get("found", False),
        "cathlab_static_present": cath,
        "playwright_chromium": pw,
        "webcvis_set": bool(cfg.cathlab_user and cfg.cathlab_pass),
        "line_set": bool(cfg.line_token),
    }


def collect(context: dict | None = None, log_lines: int = 80) -> dict:
    context = context or {}
    ver = updater.current_version()
    diag = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "version": {
            "short": ver.get("short", ""),
            "sha": ver.get("sha", ""),
            "tag": ver.get("tag", ""),
            "source": ver.get("source", ""),
            "built_at": ver.get("built_at", ""),
        },
        "frozen": updater.is_frozen(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "flags": _flags(),
        "where": scrub(str(context.get("step", "") or "")[:120]),
        "user_note": scrub(str(context.get("note", "") or "")[:1500]),
        "error": scrub(str(context.get("error", "") or "")[:2000]),
        "logs": [scrub(x) for x in log_buffer.recent(log_lines)],
    }
    return diag


# --------------------------- render ---------------------------

def render_markdown(diag: dict) -> str:
    v = diag["version"]
    f = diag["flags"]
    lines = [
        "### 環境",
        f"- 版本: `{v['short']}` ({v['source']}) tag=`{v['tag']}` "
        f"built=`{v['built_at']}`",
        f"- frozen: {diag['frozen']} | {diag['platform']} | "
        f"Python {diag['python']}",
        f"- 設定: provider={f['llm_provider']} "
        f"llm_key={f['llm_key_set']} sheet={f['sheet_id_set']} "
        f"排班sheet={f['schedule_sheet_set']} 憑證={f['creds_found']} "
        f"導管設定={f['cathlab_static_present']} "
        f"chromium={f['playwright_chromium']} "
        f"webcvis={f['webcvis_set']} line={f['line_set']}",
        "",
        "### 哪一步出問題",
        diag["where"] or "(未填)",
        "",
        "### 問題描述",
        diag["user_note"] or "(未填)",
        "",
        "### 錯誤訊息",
        "```",
        diag["error"] or "(無)",
        "```",
        "",
        "### 最近 log（已自動隱藏病歷號 / 姓名 / 金鑰）",
        "```",
        *(diag["logs"] or ["(無)"]),
        "```",
        "",
        "_此回報已自動 scrub；送出前請再掃一眼確認沒有病人資訊。_",
    ]
    return "\n".join(lines)


def build_issue_url(diag: dict) -> str:
    body = render_markdown(diag)
    if len(body) > _MAX_BODY:
        # Trim the log block first (keep the tail — newest is most useful)
        keep = diag.copy()
        logs = diag["logs"]
        while len(render_markdown(keep)) > _MAX_BODY and len(logs) > 5:
            logs = logs[len(logs) // 4:]
            keep = {**diag, "logs": logs}
        body = render_markdown(keep)
        if len(body) > _MAX_BODY:
            body = body[:_MAX_BODY] + "\n…(截斷)"
    v = diag["version"]
    title = f"[bug] {v['short'] or '?'} — {(diag['where'] or '回報')[:60]}"
    q = urllib.parse.urlencode({
        "title": title, "body": body, "labels": "bug",
    })
    return f"{_NEW_ISSUE}?{q}"


def write_report_file(diag: dict) -> Path:
    d = appconfig.DATA_DIR / "bug_reports"
    d.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = d / f"bug_report_{ts}.txt"
    path.write_text(render_markdown(diag), encoding="utf-8")
    return path
