"""Tests for updater: version discovery + check() logic.

No real git / GitHub calls — we monkeypatch _git and latest_commit.
"""
from __future__ import annotations

import json
import asyncio

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
