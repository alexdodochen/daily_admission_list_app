"""Tests for updater: version discovery + check() logic.

No real git / GitHub calls — we monkeypatch _git and latest_commit.
"""
from __future__ import annotations

import json
import asyncio
import os
import sys
from pathlib import Path

import pytest

from app.services import updater


# ---------------- current_version ----------------

def test_current_version_from_git(monkeypatch):
    def fake_git(args, cwd=updater.REPO_ROOT, timeout=30):
        if args[:2] == ["rev-parse", "HEAD"]:
            return (0, "abcdef1234567890abcdef1234567890abcdef12", "")
        if args[:2] == ["status", "--porcelain"]:
            return (0, "", "")
        return (1, "", "unexpected")
    monkeypatch.setattr(updater, "_git", fake_git)

    cur = updater.current_version()
    assert cur["source"] == "git"
    assert cur["short"] == "abcdef1"
    assert cur["dirty"] is False


def test_current_version_git_dirty(monkeypatch):
    def fake_git(args, cwd=updater.REPO_ROOT, timeout=30):
        if args[:2] == ["rev-parse", "HEAD"]:
            return (0, "0" * 40, "")
        if args[:2] == ["status", "--porcelain"]:
            return (0, " M app/main.py\n", "")
        return (1, "", "")
    monkeypatch.setattr(updater, "_git", fake_git)

    cur = updater.current_version()
    assert cur["source"] == "git"
    assert cur["dirty"] is True


def test_current_version_from_file(tmp_path, monkeypatch):
    # git fails
    monkeypatch.setattr(updater, "_git", lambda *a, **kw: (128, "", "not a repo"))
    # VERSION file present
    vf = tmp_path / "VERSION"
    vf.write_text(json.dumps({
        "sha": "1234567890abcdef",
        "built_at": "2026-04-18T09:00:00Z",
    }), encoding="utf-8")
    monkeypatch.setattr(updater, "VERSION_FILE", vf)

    cur = updater.current_version()
    assert cur["source"] == "file"
    assert cur["short"] == "1234567"
    assert cur.get("built_at") == "2026-04-18T09:00:00Z"


def test_current_version_file_plaintext_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "_git", lambda *a, **kw: (128, "", ""))
    vf = tmp_path / "VERSION"
    # Not JSON — just a raw sha
    vf.write_text("deadbeef1234567890", encoding="utf-8")
    monkeypatch.setattr(updater, "VERSION_FILE", vf)

    cur = updater.current_version()
    assert cur["source"] == "file"
    assert cur["short"] == "deadbee"


def test_current_version_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "_git", lambda *a, **kw: (128, "", ""))
    monkeypatch.setattr(updater, "VERSION_FILE", tmp_path / "does-not-exist")

    cur = updater.current_version()
    assert cur["source"] == "unknown"
    assert cur["sha"] == ""


# ---------------- check() ----------------

def test_check_update_available(monkeypatch):
    monkeypatch.setattr(updater, "current_version", lambda: {
        "sha": "aaaaaaa1111", "short": "aaaaaaa", "source": "git", "dirty": False,
    })

    def fake_remote():
        return {"sha": "bbbbbbb2222", "short": "bbbbbbb",
                "message": "feat: stuff", "date": "", "url": ""}
    monkeypatch.setattr(updater, "latest_commit", fake_remote)

    result = asyncio.run(updater.check())
    assert result["available"] is True
    assert result["current"]["short"] == "aaaaaaa"
    assert result["remote"]["short"] == "bbbbbbb"


def test_check_up_to_date(monkeypatch):
    same = "samesha1234"
    monkeypatch.setattr(updater, "current_version", lambda: {
        "sha": same, "short": same[:7], "source": "git", "dirty": False,
    })
    monkeypatch.setattr(updater, "latest_commit", lambda: {
        "sha": same, "short": same[:7], "message": "", "date": "", "url": "",
    })
    result = asyncio.run(updater.check())
    assert result["available"] is False


def test_check_unknown_local_treated_as_update(monkeypatch):
    monkeypatch.setattr(updater, "current_version", lambda: {
        "sha": "", "short": "", "source": "unknown", "dirty": False,
    })
    monkeypatch.setattr(updater, "latest_commit", lambda: {
        "sha": "remote123", "short": "remote1", "message": "", "date": "", "url": "",
    })
    result = asyncio.run(updater.check())
    # Local unknown → tell user there's an update so they get prompted
    assert result["available"] is True


def test_check_network_error_returns_error(monkeypatch):
    monkeypatch.setattr(updater, "current_version", lambda: {
        "sha": "x", "short": "x", "source": "git", "dirty": False,
    })

    def boom():
        raise RuntimeError("network down")
    monkeypatch.setattr(updater, "latest_commit", boom)

    result = asyncio.run(updater.check())
    assert result["available"] is False
    assert "network down" in result["error"]


# ---------------- apply() guards ----------------

def test_apply_refuses_non_git_install(monkeypatch):
    monkeypatch.setattr(updater, "current_version", lambda: {
        "sha": "x", "short": "x", "source": "file", "dirty": False,
    })
    result = asyncio.run(updater.apply())
    assert result["ok"] is False
    assert "git" in result["message"]


def test_apply_refuses_dirty_tree(monkeypatch):
    monkeypatch.setattr(updater, "current_version", lambda: {
        "sha": "x", "short": "x", "source": "git", "dirty": True,
    })
    result = asyncio.run(updater.apply())
    assert result["ok"] is False
    assert "未 commit" in result["message"] or "stash" in result["message"]


# ---------------- Frozen-mode release flow (new) ----------------

def test_check_frozen_compares_release_tag(monkeypatch):
    """In frozen mode, check() should call latest_release and compare tag."""
    monkeypatch.setattr(updater, "is_frozen", lambda: True)
    monkeypatch.setattr(updater, "current_version", lambda: {
        "sha": "abc", "short": "abc", "tag": "v20260101-aaaaaaa",
        "source": "file", "dirty": False,
    })
    monkeypatch.setattr(updater, "latest_release", lambda: {
        "tag": "v20260512-bbbbbbb", "sha": "bbbb",
        "asset_url": "https://example.com/x.zip", "asset_size": 100,
        "name": "v20260512-bbbbbbb", "message": "fix bug",
        "date": "2026-05-12T00:00:00Z", "short": "bbbbbbb",
        "url": "https://github.com/x/y/releases/tag/v20260512-bbbbbbb",
    })
    r = asyncio.run(updater.check())
    assert r["available"] is True
    assert r["frozen"] is True
    assert r["remote"]["tag"] == "v20260512-bbbbbbb"


def test_check_frozen_same_tag_no_update(monkeypatch):
    monkeypatch.setattr(updater, "is_frozen", lambda: True)
    monkeypatch.setattr(updater, "current_version", lambda: {
        "sha": "x", "short": "x", "tag": "v20260512-bbbbbbb",
        "source": "file", "dirty": False,
    })
    monkeypatch.setattr(updater, "latest_release", lambda: {
        "tag": "v20260512-bbbbbbb", "asset_url": "https://example.com/x.zip",
        "sha": "", "short": "", "name": "", "message": "", "date": "", "url": "",
        "asset_size": 0,
    })
    r = asyncio.run(updater.check())
    assert r["available"] is False


def test_check_frozen_missing_asset_returns_error(monkeypatch):
    """Release exists but no admission-app.zip asset → can't update."""
    monkeypatch.setattr(updater, "is_frozen", lambda: True)
    monkeypatch.setattr(updater, "current_version", lambda: {
        "sha": "x", "tag": "v1", "source": "file", "short": "x", "dirty": False,
    })
    monkeypatch.setattr(updater, "latest_release", lambda: {
        "tag": "v2", "asset_url": "",
        "sha": "", "short": "", "name": "", "message": "", "date": "", "url": "",
        "asset_size": 0,
    })
    r = asyncio.run(updater.check())
    assert r["available"] is False
    assert "asset" in r.get("error", "").lower()


def test_apply_frozen_no_asset(monkeypatch):
    monkeypatch.setattr(updater, "is_frozen", lambda: True)
    monkeypatch.setattr(updater, "latest_release", lambda: {
        "tag": "v9", "asset_url": "", "sha": "", "short": "",
        "name": "", "message": "", "date": "", "url": "", "asset_size": 0,
    })
    r = asyncio.run(updater.apply())
    assert r["ok"] is False
    assert "asset" in r["message"]


def test_schedule_restart_frozen_exits_not_execv(monkeypatch):
    """Regression: after a frozen zip-swap the swap .bat waits for THIS
    exe to vanish. os.execv would re-run the OLD exe (same image name)
    and dead-lock the bat. Frozen must os._exit, not os.execv."""
    import os as _os

    monkeypatch.setattr(updater, "is_frozen", lambda: True)
    execv_called = {}
    exit_called = {}
    monkeypatch.setattr(_os, "execv",
                        lambda *a: execv_called.setdefault("x", a))
    monkeypatch.setattr(_os, "_exit",
                        lambda code: exit_called.setdefault("code", code))

    updater.schedule_restart(delay=0.0)
    import time
    time.sleep(0.1)
    assert exit_called.get("code") == 0
    assert "x" not in execv_called


def test_schedule_restart_dev_uses_execv(monkeypatch):
    import os as _os

    monkeypatch.setattr(updater, "is_frozen", lambda: False)
    execv_called = {}
    monkeypatch.setattr(_os, "execv",
                        lambda *a: execv_called.setdefault("x", a))
    monkeypatch.setattr(_os, "_exit",
                        lambda code: (_ for _ in ()).throw(
                            AssertionError("should not _exit in dev")))
    updater.schedule_restart(delay=0.0)
    import time
    time.sleep(0.1)
    assert "x" in execv_called


# ---------------- _write_swap_bat — PowerShell migration ----------------
# 2026-05-20 field bugs (multiple bricks):
#   v1 (a68c3da):  UTF-8 .bat + chcp 65001 + IMAGENAME match. CP950 cmd
#                  parser turned Chinese exe name into mojibake → find /I
#                  never matched → wait loop forever.
#   v2 (4eae323):  OEM-encoded .bat + PID-based wait via tasklist | find.
#                  Still bricked — tasklist output parsing is unreliable
#                  across codepages and PID column alignment.
#   v3 (current):  Generate a .ps1 (PowerShell). Get-Process is a real
#                  API, no string parsing. PowerShell handles UTF-8 BOM
#                  natively → Chinese paths round-trip cleanly. .bat is
#                  now a thin ASCII shim that just launches the .ps1.
#                  Hard 60s timeout + taskkill fallback so the loop CAN
#                  NEVER spin forever again.


def test_swap_writes_ps1_alongside_bat(tmp_path, monkeypatch):
    """The swap is now driven by PowerShell. Both files should exist —
    the .bat is a thin shim that invokes the .ps1."""
    install_dir = tmp_path / "行政總醫師.排班.Key班.入院"
    install_dir.mkdir()
    pending = tmp_path / "__update_extract__" / install_dir.name
    pending.parent.mkdir()
    pending.mkdir()
    zip_path = tmp_path / "__update__.zip"
    zip_path.touch()

    monkeypatch.setattr(os, "getpid", lambda: 12345)

    bat_path = updater._write_swap_bat(install_dir, pending, zip_path,
                                       pending.parent)
    ps1_path = bat_path.parent / "__update_swap__.ps1"
    assert bat_path.exists()
    assert ps1_path.exists()


def test_swap_bat_is_ascii_only_shim(tmp_path, monkeypatch):
    """The .bat must contain only ASCII — that's the whole point of moving
    the Chinese-path logic into PowerShell. No codepage trap possible."""
    install_dir = tmp_path / "行政總醫師.排班.Key班.入院"
    install_dir.mkdir()
    pending = tmp_path / "ext" / install_dir.name
    pending.parent.mkdir()
    pending.mkdir()
    zip_path = tmp_path / "z.zip"
    zip_path.touch()

    bat_path = updater._write_swap_bat(install_dir, pending, zip_path,
                                       pending.parent)
    raw = bat_path.read_bytes()
    # raises UnicodeDecodeError if any non-ASCII bytes leaked in
    text = raw.decode("ascii")
    assert "powershell" in text.lower()
    assert "__update_swap__.ps1" in text


def test_swap_ps1_has_chinese_paths_in_utf8(tmp_path, monkeypatch):
    """The PowerShell script must carry the Chinese install path verbatim
    and be saved as UTF-8 with BOM (so PowerShell reads it correctly)."""
    install_dir = tmp_path / "行政總醫師.排班.Key班.入院"
    install_dir.mkdir()
    pending = tmp_path / "ext" / install_dir.name
    pending.parent.mkdir()
    pending.mkdir()
    zip_path = tmp_path / "z.zip"
    zip_path.touch()

    monkeypatch.setattr(os, "getpid", lambda: 12345)

    updater._write_swap_bat(install_dir, pending, zip_path, pending.parent)
    ps1_path = tmp_path / "__update_swap__.ps1"
    raw = ps1_path.read_bytes()
    # Must start with UTF-8 BOM (EF BB BF)
    assert raw[:3] == b"\xef\xbb\xbf", "PS1 must be saved UTF-8 BOM"
    text = raw.decode("utf-8-sig")
    assert "行政總醫師" in text, "Chinese path must round-trip in PS1"


def test_swap_ps1_uses_get_process_not_tasklist(tmp_path, monkeypatch):
    """Wait logic must use Get-Process (real API). Field bug: tasklist
    output parsing was the root cause of the v2 brick — output formatting
    varies and the `find " N "` heuristic was unreliable."""
    install_dir = tmp_path / "X"
    install_dir.mkdir()
    pending = tmp_path / "ext" / install_dir.name
    pending.parent.mkdir()
    pending.mkdir()
    zip_path = tmp_path / "z.zip"
    zip_path.touch()

    monkeypatch.setattr(os, "getpid", lambda: 99999)

    updater._write_swap_bat(install_dir, pending, zip_path, pending.parent)
    ps1 = (tmp_path / "__update_swap__.ps1").read_text(encoding="utf-8-sig")
    assert "$oldPid       = 99999" in ps1, "PID must be set as variable"
    assert "Get-Process -Id $oldPid" in ps1, \
        "must use Get-Process for the wait, not tasklist parsing"
    assert "Stop-Process -Id $oldPid" in ps1, \
        "must have a taskkill fallback so the loop cannot spin forever"
    assert "tasklist" not in ps1.lower(), \
        "tasklist parsing was the v2 brick path — must not appear"


def test_swap_ps1_has_bounded_wait(tmp_path):
    """A previous brick spun in an infinite wait loop because exit
    detection was broken. The new logic MUST cap the wait at 60 seconds —
    after that, the script force-kills the process and proceeds."""
    install_dir = tmp_path / "X"
    install_dir.mkdir()
    pending = tmp_path / "ext" / install_dir.name
    pending.parent.mkdir()
    pending.mkdir()
    zip_path = tmp_path / "z.zip"
    zip_path.touch()

    updater._write_swap_bat(install_dir, pending, zip_path, pending.parent)
    ps1 = (tmp_path / "__update_swap__.ps1").read_text(encoding="utf-8-sig")
    assert "60" in ps1, "must have a hard 60s timeout"
    assert "AddSeconds(60)" in ps1


def test_swap_bat_has_no_chcp_command(tmp_path, monkeypatch):
    """`chcp 65001 >nul` was a misleading no-op (only affects OUTPUT codepage,
    not how cmd PARSES the script). The new shim doesn't need it at all
    since the .bat is pure ASCII."""
    install_dir = tmp_path / "X"
    install_dir.mkdir()
    pending = tmp_path / "ext" / install_dir.name
    pending.parent.mkdir()
    pending.mkdir()
    zip_path = tmp_path / "z.zip"
    zip_path.touch()

    bat_path = updater._write_swap_bat(install_dir, pending, zip_path,
                                       pending.parent)
    text = bat_path.read_bytes().decode("ascii")
    assert "chcp 65001" not in text
