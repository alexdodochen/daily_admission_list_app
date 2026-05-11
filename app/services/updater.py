"""
商用軟體式定期更新。

- `check()` 打 GitHub API 抓 public repo 最新 commit，和本機版本比對
- `apply()` 跑 `git pull --ff-only` + 重啟 uvicorn（由前端刷新）
- 非 git checkout 的使用者（直接下載 zip）會看到提示改用 git clone

本地版本來源優先序：
  1. `git rev-parse HEAD`（若是 git checkout）
  2. `app/VERSION` 檔（tarball/zip 發布時由 CI 寫入）
  3. 都沒有 → "unknown"
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

REPO_OWNER = "alexdodochen"
REPO_NAME = "daily_admission_list_app"
API_BASE = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"
HTML_BASE = f"https://github.com/{REPO_OWNER}/{REPO_NAME}"

# repo root = parent of app/
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VERSION_FILE = REPO_ROOT / "app" / "VERSION"


def _git(args: list[str], cwd: Path = REPO_ROOT, timeout: int = 30) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True,
            timeout=timeout,
        )
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except FileNotFoundError:
        return 127, "", "git not found"
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"


def current_version() -> dict:
    """Return {sha, short, source, dirty}."""
    # 1. git HEAD
    rc, sha, _ = _git(["rev-parse", "HEAD"])
    if rc == 0 and sha:
        rc2, status, _ = _git(["status", "--porcelain"])
        dirty = bool(rc2 == 0 and status)
        return {"sha": sha, "short": sha[:7], "source": "git", "dirty": dirty}

    # 2. VERSION file
    if VERSION_FILE.exists():
        raw = VERSION_FILE.read_text(encoding="utf-8").strip()
        try:
            data = json.loads(raw)
            sha = data.get("sha", "")
            return {"sha": sha, "short": sha[:7] if sha else "",
                    "source": "file", "dirty": False,
                    "built_at": data.get("built_at", "")}
        except json.JSONDecodeError:
            return {"sha": raw, "short": raw[:7], "source": "file", "dirty": False}

    return {"sha": "", "short": "", "source": "unknown", "dirty": False}


def _fetch_json(url: str, timeout: int = 10) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": "admission-app-updater",
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def latest_remote() -> dict:
    data = _fetch_json(f"{API_BASE}/commits/main")
    commit = data.get("commit", {})
    return {
        "sha": data.get("sha", ""),
        "short": data.get("sha", "")[:7],
        "message": commit.get("message", "").split("\n")[0][:160],
        "date": commit.get("author", {}).get("date", ""),
        "url": data.get("html_url", HTML_BASE),
    }


async def check() -> dict:
    cur = current_version()
    try:
        remote = await asyncio.to_thread(latest_remote)
    except Exception as e:
        return {"available": False, "current": cur, "error": f"無法連線 GitHub：{e}"}

    cur_sha = cur.get("sha", "")
    remote_sha = remote["sha"]
    available = bool(remote_sha and cur_sha and remote_sha != cur_sha)
    if not cur_sha:
        # unknown local version → treat as update available so user sees prompt
        available = True
    return {
        "available": available,
        "current": cur,
        "remote": remote,
        "repo_url": HTML_BASE,
    }


async def apply() -> dict:
    """git pull --ff-only; caller is responsible for restarting the process."""
    cur = current_version()
    if cur["source"] != "git":
        return {
            "ok": False,
            "message": "這份 app 不是透過 git clone 安裝，自動更新只支援 git checkout。"
                       f"請從 {HTML_BASE} 重新 clone 或下載最新 zip。",
        }
    if cur.get("dirty"):
        return {
            "ok": False,
            "message": "本機有未 commit 的改動，無法自動更新。請先 `git stash` 或 commit 再試。",
        }

    # Fetch + fast-forward pull
    rc, out, err = await asyncio.to_thread(_git, ["fetch", "--prune"], REPO_ROOT, 60)
    if rc != 0:
        return {"ok": False, "message": f"git fetch 失敗：{err}"}

    rc, out, err = await asyncio.to_thread(_git, ["pull", "--ff-only"], REPO_ROOT, 60)
    if rc != 0:
        return {"ok": False, "message": f"git pull 失敗（可能分支不同步）：{err}"}

    new = current_version()
    return {
        "ok": True,
        "message": "更新完成，重新整理頁面即可使用新版。必要時請重啟 python -m app.run。",
        "from": cur.get("short", ""),
        "to": new.get("short", ""),
        "stdout": out,
    }


def schedule_restart(delay: float = 0.8) -> None:
    """Optional helper: relaunch the current Python process. Called from an API
    after a successful apply() if the user wants to auto-restart.
    Note: on Windows, os.execv replaces the current process."""
    import threading, time

    def _go():
        time.sleep(delay)
        os.execv(sys.executable, [sys.executable, "-m", "app.run"])

    threading.Thread(target=_go, daemon=True).start()
