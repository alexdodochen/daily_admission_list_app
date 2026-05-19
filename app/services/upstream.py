"""
多源（multi-source）upstream 檢查 + 同步。

本 App 依賴 3 個 GitHub repo，每次 App 啟動都會背景檢查它們的 HEAD：

  self        本 App         alexdodochen/daily_admission_list_app
  admission   入院清單上游    alexdodochen/daily-admission-list-public
  schedule    排班 / Key 班   alexdodochen/Key-Schedule-APP

對 "self" 來說 sync 等同於 `git pull --ff-only` 在 REPO_ROOT 上跑（保留舊
`updater.apply()` 的語意）。

對 "admission" / "schedule" 上游來說 sync 是把該 repo `git clone` 或
`git pull` 到本機快取目錄 EXTERNAL_DIR/<repo_name>/，然後依 `sync_manifest`
把白名單裡的「資料型」檔案複製進 app/data/static/。Python 程式碼變更不會自動
覆寫——manifest 把它們標 `needs_port`，UI 會提示開發者下次手動 port。

呼叫面：
  - check_source(name)            → dict（含 current / remote / available）
  - check_all()                   → {name: dict}
  - sync_source(name)             → dict（git pull/clone 結果 + 自動 mirror 結果）
  - sync_state()                  → 讀 integration_state.json
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from . import sync_manifest


# ----------------------------- paths -----------------------------

# REPO_ROOT = parent of app/ (the project's git checkout root)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
APP_DIR = REPO_ROOT / "app"

# 上游快取放這。dev 跟 PyInstaller frozen 都在 .exe 旁邊，避免被打包進 _MEIPASS。
if getattr(sys, "frozen", False):
    EXTERNAL_DIR = Path(sys.executable).parent / "external"
    DATA_DIR = Path(sys.executable).parent / "user_data"
else:
    EXTERNAL_DIR = REPO_ROOT / "external"
    DATA_DIR = APP_DIR / "data"

EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_PATH = DATA_DIR / "integration_state.json"

# Static-data destination root for auto-mirror.
STATIC_DEST_ROOT = DATA_DIR / "static"


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
    """Where this source's working tree lives on disk."""
    if spec.kind == "self":
        return REPO_ROOT
    return EXTERNAL_DIR / spec.name


def _is_git_checkout(p: Path) -> bool:
    return (p / ".git").exists()


# ----------------------------- current / latest -----------------------------

def current_version(spec: SourceSpec) -> dict:
    """
    Return {sha, short, source, dirty}.

    For 'self': identical behavior to legacy updater.current_version().
    For upstream: read HEAD of the cloned working tree under EXTERNAL_DIR.
    Returns source='uncloned' if upstream cache is missing.
    """
    path = repo_path(spec)

    if spec.kind == "upstream" and not _is_git_checkout(path):
        return {"sha": "", "short": "", "source": "uncloned", "dirty": False}

    rc, sha, _ = _git(["rev-parse", "HEAD"], cwd=path)
    if rc == 0 and sha:
        rc2, status, _ = _git(["status", "--porcelain"], cwd=path)
        dirty = bool(rc2 == 0 and status)
        return {"sha": sha, "short": sha[:7], "source": "git", "dirty": dirty}

    # self only: VERSION file fallback (used by PyInstaller bundles)
    if spec.kind == "self":
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
    if cur["source"] == "uncloned":
        # 還沒 clone 過上游 → 視為「有更新待同步」
        available = bool(remote_sha)
    elif not cur_sha:
        available = bool(remote_sha)   # 本地未知版本，提示同步
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
    spec = SOURCES[name]
    if spec.kind == "self":
        return await _sync_self(spec)
    return await _sync_upstream(spec)


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


async def _sync_upstream(spec: SourceSpec) -> dict:
    """Clone if missing, otherwise fetch+reset to origin/<branch>. Then run the
    auto-mirror manifest for this source."""
    path = repo_path(spec)
    EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)

    if not _is_git_checkout(path):
        # Fresh clone (shallow, single branch — keeps download small)
        if path.exists():
            # Path exists but isn't a git checkout — refuse to nuke it
            return {"ok": False,
                    "message": f"{path} 已存在但不是 git checkout，請手動移除後再試。"}
        rc, out, err = await asyncio.to_thread(
            _git, ["clone", "--depth", "1", "--branch", spec.branch,
                   spec.clone_url, str(path)],
            cwd=EXTERNAL_DIR, timeout=180,
        )
        if rc != 0:
            return {"ok": False, "message": f"git clone 失敗：{err}"}
    else:
        # Update existing checkout. Use fetch + reset --hard origin/<branch>
        # so that any local divergence (this dir is dev-managed, not ours) is
        # discarded — upstream is source of truth.
        rc, _, err = await asyncio.to_thread(
            _git, ["fetch", "--prune", "--depth", "1", "origin", spec.branch],
            cwd=path, timeout=120,
        )
        if rc != 0:
            return {"ok": False, "message": f"git fetch 失敗：{err}"}
        rc, _, err = await asyncio.to_thread(
            _git, ["reset", "--hard", f"origin/{spec.branch}"],
            cwd=path, timeout=60,
        )
        if rc != 0:
            return {"ok": False, "message": f"git reset 失敗：{err}"}

    # Mirror auto-safe files into app/data/static/
    cur = current_version(spec)
    mirrored, mirror_errors = _run_mirror(spec, path)
    _record_sync(spec.key, cur.get("sha", ""), mirrored)

    return {
        "ok": True,
        "message": f"上游 {spec.name} 同步成功（{cur.get('short','')}），"
                   f"mirror {len(mirrored)} 檔" +
                   (f"，{len(mirror_errors)} 檔失敗" if mirror_errors else ""),
        "to": cur.get("short", ""),
        "mirrored": mirrored,
        "mirror_errors": mirror_errors,
        "needs_port": sync_manifest.MANIFEST.get(spec.key, {}).get("needs_port", []),
    }


def _run_mirror(spec: SourceSpec, repo_root: Path) -> tuple[list[str], list[dict]]:
    """Copy whitelisted files from the cloned upstream into DATA_DIR.
    Manifest dest paths are relative to DATA_DIR (e.g. 'static/foo.json' →
    DATA_DIR/static/foo.json). Returns (mirrored_paths, errors)."""
    mirrored: list[str] = []
    errors: list[dict] = []
    rules = sync_manifest.MANIFEST.get(spec.key, {}).get("auto_mirror", [])
    for src_rel, dest_rel in rules:
        src = repo_root / src_rel
        dest = DATA_DIR / dest_rel
        try:
            if not src.exists():
                errors.append({"src": src_rel, "error": "上游檔案不存在"})
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            mirrored.append(dest_rel)
        except Exception as e:
            errors.append({"src": src_rel, "error": str(e)})
    return mirrored, errors


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
