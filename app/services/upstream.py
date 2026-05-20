"""
Self-source updater for this app.

Since the 2026-05-18 sync-source cutover, `daily_admission_list_app` is the
SINGLE source of truth — the old multi-repo mirroring of
`daily-admission-list-public` / `Key-Schedule-APP` is retired. This module
keeps the `check_*` / `sync_*` shape that the topbar JS expects, but only
the `self` source is wired.

Call surface:
  - check_source('self')      → dict (current / remote / available)
  - check_all()               → {'self': dict}
  - sync_source('self')       → dict (git pull --ff-only, or frozen-bundle swap)
  - sync_state()              → read integration_state.json
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ----------------------------- paths -----------------------------

# REPO_ROOT = parent of app/ (the project's git checkout root)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
APP_DIR = REPO_ROOT / "app"

if getattr(sys, "frozen", False):
    DATA_DIR = Path(sys.executable).parent / "user_data"
else:
    DATA_DIR = APP_DIR / "data"

DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_PATH = DATA_DIR / "integration_state.json"


# ----------------------------- source registry -----------------------------

@dataclass(frozen=True)
class SourceSpec:
    key: str            # 'self' | 'admission' | 'schedule'
    owner: str
    name: str           # GitHub repo name
    branch: str
    label: str          # 中文 UI 標籤
    feature: str        # 對應的 App 功能（給 UI 顯示）
    kind: str           # 'self' | 'upstream'

    @property
    def html_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.name}"

    @property
    def api_base(self) -> str:
        return f"https://api.github.com/repos/{self.owner}/{self.name}"

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.name}.git"


# 2026-05-18: sync-source cutover (user directive). The project repo
# `daily_admission_list_app` is now the SINGLE source of truth — the old
# multi-repo upstream check (daily-admission-list-public / Key-Schedule-APP)
# is retired. Only `self` remains so the topbar bar only ever reports the
# app's own repo. See memory feedback_card1_sync_source_cutover.
SOURCES: dict[str, SourceSpec] = {
    "self": SourceSpec(
        key="self",
        owner="alexdodochen",
        name="daily_admission_list_app",
        branch="main",
        label="本 App",
        feature="App 本體",
        kind="self",
    ),
}


# ----------------------------- git + http helpers -----------------------------

def _git(args: list[str], cwd: Path, timeout: int = 60) -> tuple[int, str, str]:
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


def _fetch_json(url: str, timeout: int = 10) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": "admission-app-updater",
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ----------------------------- per-source repo path -----------------------------

def repo_path(spec: SourceSpec) -> Path:
    """Where this source's working tree lives on disk. Only `self` is wired
    since the 2026-05-18 cutover, so always returns REPO_ROOT."""
    return REPO_ROOT


def _is_git_checkout(p: Path) -> bool:
    return (p / ".git").exists()


# ----------------------------- current / latest -----------------------------

def current_version(spec: SourceSpec) -> dict:
    """
    Return {sha, short, source, dirty}.

    Git checkout → HEAD sha (preferred).
    PyInstaller frozen bundle → app/VERSION file fallback.
    """
    path = repo_path(spec)
    rc, sha, _ = _git(["rev-parse", "HEAD"], cwd=path)
    if rc == 0 and sha:
        rc2, status, _ = _git(["status", "--porcelain"], cwd=path)
        dirty = bool(rc2 == 0 and status)
        return {"sha": sha, "short": sha[:7], "source": "git", "dirty": dirty}

    # VERSION file fallback for PyInstaller bundles
    version_file = APP_DIR / "VERSION"
    if version_file.exists():
        raw = version_file.read_text(encoding="utf-8").strip()
        try:
            data = json.loads(raw)
            vsha = data.get("sha", "")
            return {"sha": vsha, "short": vsha[:7] if vsha else "",
                    "source": "file", "dirty": False,
                    "built_at": data.get("built_at", "")}
        except json.JSONDecodeError:
            return {"sha": raw, "short": raw[:7], "source": "file", "dirty": False}

    return {"sha": "", "short": "", "source": "unknown", "dirty": False}


def latest_remote(spec: SourceSpec) -> dict:
    data = _fetch_json(f"{spec.api_base}/commits/{spec.branch}")
    commit = data.get("commit", {})
    return {
        "sha": data.get("sha", ""),
        "short": data.get("sha", "")[:7],
        "message": commit.get("message", "").split("\n")[0][:160],
        "date": commit.get("author", {}).get("date", ""),
        "url": data.get("html_url", spec.html_url),
    }


def commits_between(spec: SourceSpec, base_sha: str, head_sha: str,
                    limit: int = 20) -> list[dict]:
    """Pull short list of commits between base..head via GitHub Compare API.
    Returns up to `limit` newest. Empty list on any error."""
    if not base_sha or not head_sha or base_sha == head_sha:
        return []
    try:
        data = _fetch_json(
            f"{spec.api_base}/compare/{base_sha}...{head_sha}", timeout=10)
        out = []
        for c in (data.get("commits") or [])[-limit:]:
            out.append({
                "sha": c.get("sha", "")[:7],
                "message": (c.get("commit") or {}).get("message", "").split("\n")[0][:140],
                "url": c.get("html_url", ""),
            })
        return list(reversed(out))   # newest first
    except Exception:
        return []


# ----------------------------- check / check_all -----------------------------

async def check_source(name: str) -> dict:
    spec = SOURCES[name]
    cur = current_version(spec)
    state = sync_state().get(spec.key, {})
    last_synced_sha = state.get("sha", "")
    last_synced_at = state.get("synced_at", "")

    try:
        remote = await asyncio.to_thread(latest_remote, spec)
    except Exception as e:
        return {
            "name": spec.key, "label": spec.label, "feature": spec.feature,
            "kind": spec.kind, "url": spec.html_url,
            "current": cur, "remote": None,
            "last_synced": {"sha": last_synced_sha, "at": last_synced_at},
            "available": False, "error": f"無法連線 GitHub：{e}",
        }

    cur_sha = cur.get("sha", "") or last_synced_sha
    remote_sha = remote.get("sha", "")
    if not cur_sha:
        available = bool(remote_sha)   # local version unknown, prompt sync
    else:
        available = bool(remote_sha and remote_sha != cur_sha)

    new_commits = []
    if available and cur_sha and remote_sha:
        new_commits = await asyncio.to_thread(
            commits_between, spec, cur_sha, remote_sha, 20)

    return {
        "name": spec.key, "label": spec.label, "feature": spec.feature,
        "kind": spec.kind, "url": spec.html_url,
        "current": cur, "remote": remote,
        "last_synced": {"sha": last_synced_sha, "at": last_synced_at},
        "available": available, "new_commits": new_commits,
    }


async def check_all() -> dict:
    results = await asyncio.gather(
        *[check_source(name) for name in SOURCES.keys()],
        return_exceptions=True,
    )
    out: dict[str, dict] = {}
    for name, r in zip(SOURCES.keys(), results):
        if isinstance(r, Exception):
            out[name] = {
                "name": name, "label": SOURCES[name].label,
                "feature": SOURCES[name].feature, "kind": SOURCES[name].kind,
                "url": SOURCES[name].html_url,
                "current": {"sha": "", "short": "", "source": "unknown", "dirty": False},
                "remote": None, "available": False,
                "error": f"check 失敗：{r}",
                "last_synced": {"sha": "", "at": ""},
            }
        else:
            out[name] = r
    return out


# ----------------------------- sync state file -----------------------------

def sync_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_state(state: dict) -> None:
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _record_sync(name: str, sha: str, mirrored: list[str]) -> None:
    s = sync_state()
    s[name] = {
        "sha": sha,
        "synced_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mirrored": mirrored,
    }
    _write_state(s)


# ----------------------------- sync -----------------------------

async def sync_source(name: str) -> dict:
    return await _sync_self(SOURCES[name])


async def _sync_self(spec: SourceSpec) -> dict:
    """Update the running App.

    Packaged (.exe) install → delegate to updater._apply_frozen(), which
    downloads the latest GitHub Release zip and hot-swaps the bundle. The
    distributed artifact is NOT a git checkout, so the git-pull path below
    can never apply to it (this was the field bug: the 更新 button hit the
    git-only path and dead-ended with "只支援 git checkout").

    Dev (git checkout) → git pull --ff-only (legacy updater.apply semantics).
    """
    from . import updater  # local import avoids any import cycle
    if updater.is_frozen():
        return await updater.apply()

    cur = current_version(spec)
    if cur["source"] != "git":
        return {
            "ok": False,
            "message": "這份 App 不是透過 git clone 安裝，自動更新只支援 git checkout。"
                       f"請從 {spec.html_url} 重新 clone 或下載最新 zip。",
        }
    if cur.get("dirty"):
        return {
            "ok": False,
            "message": "本機有未 commit 的改動，無法自動更新。請先 `git stash` 或 commit 再試。",
        }

    rc, _, err = await asyncio.to_thread(_git, ["fetch", "--prune"], REPO_ROOT, 60)
    if rc != 0:
        return {"ok": False, "message": f"git fetch 失敗：{err}"}
    rc, out, err = await asyncio.to_thread(_git, ["pull", "--ff-only"], REPO_ROOT, 60)
    if rc != 0:
        return {"ok": False, "message": f"git pull 失敗（可能分支不同步）：{err}"}

    new = current_version(spec)
    _record_sync(spec.key, new.get("sha", ""), [])
    return {
        "ok": True,
        "message": "更新完成，重新整理頁面即可使用新版。必要時請重啟 python -m app.run。",
        "from": cur.get("short", ""),
        "to": new.get("short", ""),
        "stdout": out,
    }


# ----------------------------- back-compat shims -----------------------------
# Keep the legacy single-source updater API working so existing tests (which
# patch updater._git / updater.latest_remote) still pass.

async def check() -> dict:
    """Legacy: just return the 'self' source check, in old shape."""
    spec = SOURCES["self"]
    cur = current_version(spec)
    try:
        remote = await asyncio.to_thread(latest_remote, spec)
    except Exception as e:
        return {"available": False, "current": cur,
                "error": f"無法連線 GitHub：{e}"}
    cur_sha = cur.get("sha", "")
    remote_sha = remote.get("sha", "")
    available = bool(remote_sha and cur_sha and remote_sha != cur_sha)
    if not cur_sha:
        available = True
    return {"available": available, "current": cur, "remote": remote,
            "repo_url": spec.html_url}


async def apply() -> dict:
    """Legacy: same as sync_source('self')."""
    return await _sync_self(SOURCES["self"])
