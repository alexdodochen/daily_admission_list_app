"""
Self-updating distribution.

Two execution modes, auto-detected via `sys.frozen`:

  Dev (`python -m app.run`):
    - check() compares local git HEAD with origin/main on GitHub.
    - apply() runs `git pull --ff-only` and lets the caller restart.

  Packaged (.exe via PyInstaller):
    - check() compares the local VERSION file with the latest GitHub
      Release tag.
    - apply() downloads the new release zip asset, extracts it next to
      the running install, writes a swap .bat that waits for this
      process to exit, renames folders, and relaunches the new .exe.

Local version resolution:
  1. `git rev-parse HEAD` (only useful in dev)
  2. `app/VERSION` (written by CI at build time — JSON with sha+built_at)
  3. fallback "unknown"
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

REPO_OWNER = "alexdodochen"
REPO_NAME = "daily_admission_list_app"
API_BASE = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"
HTML_BASE = f"https://github.com/{REPO_OWNER}/{REPO_NAME}"

# Release-asset filename uploaded by the GitHub Actions workflow.
# MUST stay ASCII — a non-ASCII asset name gets mangled to "default.zip"
# by action-gh-release, and `latest_release()` matches assets by exact
# name. The Chinese bundle folder/exe (行政總醫師.排班.Key班.入院) live
# INSIDE this zip; only the asset filename is ASCII. Must equal the
# DestinationPath in .github/workflows/release.yml "Zip distribution".
RELEASE_ASSET_NAME = "admission-app.zip"

# repo root = parent of app/
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VERSION_FILE = REPO_ROOT / "app" / "VERSION"


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


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
    """Return {sha, short, tag, source, dirty, built_at}."""
    # 1. git HEAD (only meaningful in dev / non-frozen)
    if not is_frozen():
        rc, sha, _ = _git(["rev-parse", "HEAD"])
        if rc == 0 and sha:
            rc2, status, _ = _git(["status", "--porcelain"])
            dirty = bool(rc2 == 0 and status)
            return {"sha": sha, "short": sha[:7], "tag": "",
                    "source": "git", "dirty": dirty, "built_at": ""}

    # 2. VERSION file (written by the CI build)
    if VERSION_FILE.exists():
        raw = VERSION_FILE.read_text(encoding="utf-8").strip()
        try:
            data = json.loads(raw)
            sha = data.get("sha", "")
            return {"sha": sha, "short": sha[:7] if sha else "",
                    "tag": data.get("tag", ""),
                    "source": "file", "dirty": False,
                    "built_at": data.get("built_at", "")}
        except json.JSONDecodeError:
            return {"sha": raw, "short": raw[:7], "tag": "",
                    "source": "file", "dirty": False, "built_at": ""}

    return {"sha": "", "short": "", "tag": "",
            "source": "unknown", "dirty": False, "built_at": ""}


def _fetch_json(url: str, timeout: int = 10) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": "admission-app-updater",
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def latest_commit() -> dict:
    """Latest commit on main (used for dev/git-checkout flow)."""
    data = _fetch_json(f"{API_BASE}/commits/main")
    commit = data.get("commit", {})
    return {
        "sha": data.get("sha", ""),
        "short": data.get("sha", "")[:7],
        "message": commit.get("message", "").split("\n")[0][:160],
        "date": commit.get("author", {}).get("date", ""),
        "url": data.get("html_url", HTML_BASE),
    }


def latest_release() -> dict:
    """Latest GitHub Release with the bundled-exe asset attached."""
    data = _fetch_json(f"{API_BASE}/releases/latest")
    assets = data.get("assets", [])
    target = next((a for a in assets if a.get("name") == RELEASE_ASSET_NAME), None)
    return {
        "tag":     data.get("tag_name", ""),
        "name":    data.get("name", ""),
        "sha":     (data.get("target_commitish", "") or "")[:40],
        "short":   (data.get("target_commitish", "") or "")[:7],
        "message": (data.get("body", "") or "").split("\n")[0][:160],
        "date":    data.get("published_at", ""),
        "url":     data.get("html_url", HTML_BASE),
        "asset_url":  (target or {}).get("browser_download_url", ""),
        "asset_size": (target or {}).get("size", 0),
    }


async def check() -> dict:
    cur = current_version()
    frozen = is_frozen()
    try:
        remote = await asyncio.to_thread(latest_release if frozen else latest_commit)
    except Exception as e:
        return {"available": False, "current": cur, "frozen": frozen,
                "error": f"無法連線 GitHub：{e}"}

    if frozen:
        # Frozen builds compare against release tag (set in VERSION at build time).
        cur_tag = cur.get("tag", "") or cur.get("sha", "")
        remote_tag = remote.get("tag", "")
        available = bool(remote_tag and cur_tag and remote_tag != cur_tag)
        if not cur_tag:
            available = True
        if not remote.get("asset_url"):
            return {"available": False, "current": cur, "remote": remote,
                    "frozen": True,
                    "error": f"GitHub release 沒有 {RELEASE_ASSET_NAME} asset，跳過自動更新"}
    else:
        cur_sha = cur.get("sha", "")
        remote_sha = remote.get("sha", "")
        available = bool(remote_sha and cur_sha and remote_sha != cur_sha)
        if not cur_sha:
            available = True
    return {
        "available": available,
        "current": cur,
        "remote": remote,
        "frozen": frozen,
        "repo_url": HTML_BASE,
    }


# ----------------------------- dev (git) update -----------------------------

async def _apply_git() -> dict:
    cur = current_version()
    if cur["source"] != "git":
        return {
            "ok": False,
            "message": "這份 app 不是透過 git clone 安裝。請改用 .exe 自動更新，"
                       f"或從 {HTML_BASE} 重新 clone。",
        }
    if cur.get("dirty"):
        return {
            "ok": False,
            "message": "本機有未 commit 的改動，無法自動更新。請先 `git stash` 或 commit 再試。",
        }

    rc, _out, err = await asyncio.to_thread(_git, ["fetch", "--prune"], REPO_ROOT, 60)
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


# ----------------------------- frozen (.exe) update -----------------------------

def _download_to(url: str, dest: Path) -> None:
    """Stream-download to dest with progress (no third-party deps)."""
    req = urllib.request.Request(url, headers={"User-Agent": "admission-app-updater"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as f:
        shutil.copyfileobj(resp, f, length=1 << 20)


def _write_swap_bat(install_dir: Path,
                    pending_inner: Path,
                    zip_path: Path,
                    extract_dir: Path) -> Path:
    """
    Generate a .bat that:
      - Waits for the running .exe process to exit (by PID — ASCII-safe)
      - Renames current install_dir → install_dir.old
      - Moves pending_inner → install_dir
      - Cleans up zip + extract scratch + .old
      - Relaunches the new .exe
      - Deletes itself

    install_dir = the .exe folder currently running
                  (e.g. C:\\...\\行政總醫師.排班.Key班.入院)
    pending_inner = the freshly-extracted same-named subfolder
    zip_path = the downloaded .zip
    extract_dir = parent of pending_inner (scratch dir)

    *Codepage trap* (field bug 2026-05-20 — bricked an install):
    cmd.exe parses .bat files using the system's *active console* codepage
    (CP950 on Traditional-Chinese Windows), NOT what `chcp 65001` says.
    So a UTF-8 .bat with Chinese paths becomes mojibake at parse time,
    `find /I` never matches the real process name, the wait loop spins
    forever, and the swap never completes.

    Two-pronged fix:
      1. Wait by PID (`tasklist /FI "PID eq N"`) — number is ASCII, never
         hits the codepage issue regardless of folder language.
      2. Write the .bat in the OEM codepage (Windows: GetOEMCP() → 950
         on TW) so cmd.exe reads the Chinese paths in `ren` / `move` /
         `start` lines as the bytes it expects. Fallback to ANSI codepage,
         then to UTF-8 with BOM if both lookups fail.
    """
    import os as _os
    exe_name = install_dir.name + ".exe"   # 行政總醫師.排班.Key班.入院.exe
    parent = install_dir.parent
    bat_path = parent / "__update_swap__.bat"

    current_pid = _os.getpid()

    bat = f"""@echo off
cd /d "{parent}"
echo Waiting for current app (PID {current_pid}) to exit...
:waitloop
tasklist /FI "PID eq {current_pid}" 2>nul | find " {current_pid} " >nul
if not errorlevel 1 (
  timeout /t 1 /nobreak >nul
  goto waitloop
)
echo Swapping install...
ren "{install_dir.name}" "{install_dir.name}.old"
if errorlevel 1 (
  echo [ERR] cannot rename old install. Aborting.
  pause
  exit /b 1
)
move "{pending_inner}" "{install_dir}"
if errorlevel 1 (
  echo [ERR] cannot move new install. Rolling back.
  ren "{install_dir.name}.old" "{install_dir.name}"
  pause
  exit /b 1
)
rmdir /s /q "{install_dir}.old" 2>nul
rmdir /s /q "{extract_dir}" 2>nul
del /q "{zip_path}" 2>nul
echo Restarting...
start "" "{install_dir}\\{exe_name}"
del "%~f0"
"""
    _write_bat_in_console_codepage(bat_path, bat)
    return bat_path


def _write_bat_in_console_codepage(bat_path: Path, content: str) -> None:
    """Write the .bat using whatever encoding cmd.exe will actually read it
    as. On Windows that's the OEM codepage (CP950 on Traditional-Chinese
    systems); on non-Windows we just use UTF-8 (the script will never run
    there but the dev test harness still touches it).

    Falls back gracefully: OEM cp → ANSI cp → UTF-8 with BOM.
    Any chars that can't round-trip in the chosen codepage are XML-escaped
    so cmd at worst sees a literal `&#NNNN;` rather than corrupted bytes.
    """
    if sys.platform != "win32":
        bat_path.write_text(content, encoding="utf-8")
        return
    try:
        import ctypes
        oem_cp = ctypes.windll.kernel32.GetOEMCP()
        encoding = f"cp{oem_cp}"
        bat_path.write_text(content, encoding=encoding, errors="xmlcharrefreplace")
        return
    except Exception:
        pass
    try:
        import ctypes
        ansi_cp = ctypes.windll.kernel32.GetACP()
        bat_path.write_text(content, encoding=f"cp{ansi_cp}",
                            errors="xmlcharrefreplace")
        return
    except Exception:
        pass
    bat_path.write_text("﻿" + content, encoding="utf-8")


async def _apply_frozen() -> dict:
    """Download the latest release asset, stage it, launch swap script, exit."""
    try:
        remote = await asyncio.to_thread(latest_release)
    except Exception as e:
        return {"ok": False, "message": f"無法取得 GitHub release：{e}"}

    asset_url = remote.get("asset_url")
    if not asset_url:
        return {"ok": False, "message": f"最新 release ({remote.get('tag','?')}) "
                                        f"沒有 {RELEASE_ASSET_NAME} asset。"}

    install_dir = Path(sys.executable).parent.resolve()
    parent = install_dir.parent
    zip_path = parent / "__update__.zip"
    extract_dir = parent / "__update_extract__"

    # Clean leftovers from a previous failed update
    if extract_dir.exists():
        shutil.rmtree(extract_dir, ignore_errors=True)
    if zip_path.exists():
        zip_path.unlink(missing_ok=True)

    try:
        await asyncio.to_thread(_download_to, asset_url, zip_path)
    except Exception as e:
        return {"ok": False, "message": f"下載失敗：{e}"}

    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(extract_dir)
    except Exception as e:
        return {"ok": False, "message": f"解壓失敗：{e}"}

    # Expect extract_dir/<bundle>/<bundle>.exe (bundle = install_dir.name)
    pending_inner = extract_dir / install_dir.name
    if not (pending_inner / f"{install_dir.name}.exe").exists():
        # Fall back: try any single top-level folder inside the zip
        subdirs = [d for d in extract_dir.iterdir() if d.is_dir()]
        if len(subdirs) == 1 and (subdirs[0] / f"{install_dir.name}.exe").exists():
            pending_inner = subdirs[0]
        else:
            return {"ok": False, "message":
                    f"zip 結構不對：找不到 {install_dir.name}.exe in {extract_dir}"}

    bat_path = _write_swap_bat(install_dir, pending_inner, zip_path, extract_dir)

    # Launch the .bat detached, then exit ourselves so it can rename our folder.
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    subprocess.Popen(["cmd.exe", "/c", str(bat_path)],
                     cwd=str(parent), creationflags=flags,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True)

    return {
        "ok": True,
        "message": "已下載新版，正在切換並重啟。請稍候新視窗自動開啟。",
        "from": current_version().get("tag", ""),
        "to":   remote.get("tag", ""),
        "frozen": True,
    }


async def apply() -> dict:
    """Top-level apply — dispatches to git or frozen-mode update."""
    if is_frozen():
        return await _apply_frozen()
    return await _apply_git()


def schedule_restart(delay: float = 1.5) -> None:
    """Restart/quit the running process after a successful apply().

    Frozen (.exe): _apply_frozen() has already spawned a detached swap
    .bat that waits for THIS exe to disappear from the task list, then
    renames the folder and relaunches the new exe. So here we must just
    cleanly EXIT — never os.execv the frozen exe (that re-runs the OLD
    bundle with junk args and keeps the same image name alive, so the
    bat's wait-loop never completes and the update dead-locks).

    Dev (git checkout): re-exec the Python module so the new code loads.
    """
    import threading, time

    def _go():
        time.sleep(delay)
        if is_frozen():
            os._exit(0)   # let the swap .bat take over (rename + relaunch)
        else:
            os.execv(sys.executable, [sys.executable, "-m", "app.run"])

    threading.Thread(target=_go, daemon=True).start()
