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


# ---------------- _write_swap_bat — codepage + PID-wait regression ----------------
# Field bug 2026-05-20: the swap .bat was written UTF-8 and used IMAGENAME
# matching, but cmd.exe on TW Windows parses .bat in CP950 → Chinese path
# became mojibake → find /I never matched → bat froze in wait loop → app
# bricked (old exe already os._exit'd, new exe never relaunched).
#
# Two invariants we now pin:
#   1. Wait condition is PID-based ('tasklist /FI "PID eq N"'), NEVER
#      IMAGENAME-based — PIDs are ASCII digits and survive any codepage.
#   2. The .bat content is written with a codepage that round-trips the
#      Chinese install dir name to BYTES cmd.exe will read correctly.
#      On Windows this means OEM codepage; non-Windows we keep utf-8 for
#      the dev-test harness.


def test_swap_bat_waits_by_pid_not_imagename(tmp_path, monkeypatch):
    """Wait loop MUST filter by PID. Field bug: IMAGENAME with Chinese
    filename never matched after codepage corruption."""
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
    assert bat_path.exists()
    # Read with utf-8 errors=replace just to look at the structure; the
    # PID number itself is always ASCII so this read is safe.
    raw = bat_path.read_bytes()
    text = raw.decode("ascii", errors="replace")
    assert 'PID eq 12345' in text, \
        "wait loop must filter by PID, not IMAGENAME (codepage-fragile)"
    assert "12345" in text
    # The OLD logic used `tasklist /FI "IMAGENAME eq <exe_name>"` and then
    # `find /I "<exe_name>"`. After the fix, IMAGENAME should not appear.
    assert "IMAGENAME" not in text, \
        "IMAGENAME match was the codepage-fragile path (2026-05-20 brick)"


def test_swap_bat_chinese_paths_roundtrip_in_oem_codepage(tmp_path, monkeypatch):
    """The .bat must encode Chinese install path in a codepage cmd.exe will
    read correctly. On Windows that's the OEM codepage; we check the file
    round-trips back to the original characters."""
    install_dir = tmp_path / "行政總醫師.排班.Key班.入院"
    install_dir.mkdir()
    pending = tmp_path / "__update_extract__" / install_dir.name
    pending.parent.mkdir()
    pending.mkdir()
    zip_path = tmp_path / "__update__.zip"
    zip_path.touch()

    bat_path = updater._write_swap_bat(install_dir, pending, zip_path,
                                       pending.parent)
    raw = bat_path.read_bytes()

    # The file should be readable in SOME encoding that round-trips the
    # Chinese name. Try OEM (Windows) → ANSI → UTF-8 with BOM.
    candidates = []
    if sys.platform == "win32":
        try:
            import ctypes
            candidates.append(f"cp{ctypes.windll.kernel32.GetOEMCP()}")
            candidates.append(f"cp{ctypes.windll.kernel32.GetACP()}")
        except Exception:
            pass
    candidates.append("utf-8-sig")
    candidates.append("utf-8")

    decoded = None
    for cp in candidates:
        try:
            decoded = raw.decode(cp)
            if "行政總醫師" in decoded:
                break
        except Exception:
            continue
    assert decoded is not None, "bat must decode in at least one common cp"
    assert "行政總醫師" in decoded, \
        "Chinese folder name must survive the chosen file encoding"
    # The previous bug was producing UTF-8 bytes which, when decoded as
    # CP950, became mojibake like '鈞蝮虜揮'. With the fix we should
    # never see those characters in the file.
    assert "鈞" not in decoded, "mojibake leaked through the encoder"


def test_swap_bat_has_no_chcp_command(tmp_path, monkeypatch):
    """`chcp 65001 >nul` was a misleading no-op (only affects OUTPUT codepage,
    not how cmd PARSES the script). Removing it both shortens startup and
    avoids the false impression the script is codepage-safe."""
    install_dir = tmp_path / "X"
    install_dir.mkdir()
    pending = tmp_path / "ext" / install_dir.name
    pending.parent.mkdir()
    pending.mkdir()
    zip_path = tmp_path / "z.zip"
    zip_path.touch()

    bat_path = updater._write_swap_bat(install_dir, pending, zip_path,
                                       pending.parent)
    raw = bat_path.read_bytes()
    text = raw.decode("ascii", errors="replace")
    assert "chcp 65001" not in text, \
        "chcp 65001 was the misleading 'fix' that didn't actually work"
