"""Tests for the upstream module.

2026-05-18 sync-source cutover: the multi-repo upstream check
(daily-admission-list-public / Key-Schedule-APP) is retired. The project
repo `daily_admission_list_app` is the single source of truth, so
`upstream.SOURCES` now contains only `self`. Tests that exercised the
removed `admission` / `schedule` sources and the upstream-mirror feature
were dropped accordingly. See memory feedback_card1_sync_source_cutover.
"""
from __future__ import annotations

import asyncio
import json

from app.services import upstream


# ---------------- registry ----------------

def test_only_self_source():
    assert set(upstream.SOURCES.keys()) == {"self"}
    self_spec = upstream.SOURCES["self"]
    assert self_spec.name == "daily_admission_list_app"
    assert self_spec.kind == "self"


def test_self_source_urls():
    s = upstream.SOURCES["self"]
    assert s.html_url == "https://github.com/alexdodochen/daily_admission_list_app"
    assert s.api_base == "https://api.github.com/repos/alexdodochen/daily_admission_list_app"
    assert s.clone_url == "https://github.com/alexdodochen/daily_admission_list_app.git"


# ---------------- current_version ----------------

def test_current_version_self_from_git(monkeypatch):
    spec = upstream.SOURCES["self"]
    def fake_git(args, cwd, timeout=60):
        if args[:2] == ["rev-parse", "HEAD"]:
            return (0, "a" * 40, "")
        if args[:2] == ["status", "--porcelain"]:
            return (0, "", "")
        return (1, "", "unexpected")
    monkeypatch.setattr(upstream, "_git", fake_git)
    cur = upstream.current_version(spec)
    assert cur["source"] == "git"
    assert cur["short"] == "a" * 7
    assert cur["dirty"] is False


# ---------------- check_source ----------------

def test_check_source_self_available(monkeypatch):
    monkeypatch.setattr(upstream, "current_version", lambda spec: {
        "sha": "old" + "0" * 37, "short": "old0000", "source": "git", "dirty": False,
    })
    monkeypatch.setattr(upstream, "latest_remote", lambda spec: {
        "sha": "new" + "0" * 37, "short": "new0000",
        "message": "feat: thing", "date": "", "url": "",
    })
    monkeypatch.setattr(upstream, "commits_between",
                        lambda spec, base, head, limit=20: [
                            {"sha": "abc1234", "message": "msg", "url": ""},
                        ])
    monkeypatch.setattr(upstream, "sync_state", lambda: {})
    r = asyncio.run(upstream.check_source("self"))
    assert r["available"] is True
    assert r["name"] == "self"
    assert r["current"]["short"] == "old0000"
    assert r["remote"]["short"] == "new0000"
    assert len(r["new_commits"]) == 1


def test_check_source_network_error(monkeypatch):
    monkeypatch.setattr(upstream, "current_version", lambda spec: {
        "sha": "x", "short": "x", "source": "git", "dirty": False,
    })
    def boom(spec):
        raise RuntimeError("offline")
    monkeypatch.setattr(upstream, "latest_remote", boom)
    monkeypatch.setattr(upstream, "sync_state", lambda: {})
    r = asyncio.run(upstream.check_source("self"))
    assert r["available"] is False
    assert "offline" in r["error"]


# ---------------- check_all ----------------

def test_check_all_returns_only_self(monkeypatch):
    monkeypatch.setattr(upstream, "current_version", lambda spec: {
        "sha": "x" * 40, "short": "x" * 7, "source": "git", "dirty": False,
    })
    monkeypatch.setattr(upstream, "latest_remote", lambda spec: {
        "sha": "x" * 40, "short": "x" * 7, "message": "", "date": "", "url": "",
    })
    monkeypatch.setattr(upstream, "sync_state", lambda: {})
    out = asyncio.run(upstream.check_all())
    assert set(out.keys()) == {"self"}
    for v in out.values():
        assert v["available"] is False


# ---------------- sync_state read/write ----------------

def test_sync_state_roundtrip(tmp_path, monkeypatch):
    state_path = tmp_path / "integration_state.json"
    monkeypatch.setattr(upstream, "STATE_PATH", state_path)
    assert upstream.sync_state() == {}
    upstream._record_sync("self", "abc1234", [])
    on_disk = json.loads(state_path.read_text(encoding="utf-8"))
    assert on_disk["self"]["sha"] == "abc1234"
    assert "synced_at" in on_disk["self"]


# ---------------- frozen self-sync delegates to updater ----------------

def test_sync_self_frozen_delegates_to_updater(monkeypatch):
    """Regression (field bug): on a packaged .exe the 更新 button hit the
    git-only path and dead-ended with '只支援 git checkout'. Frozen must
    delegate to updater.apply() (the GitHub-Release zip swap)."""
    from app.services import updater

    monkeypatch.setattr(updater, "is_frozen", lambda: True)
    called = {}

    async def fake_apply():
        called["yes"] = True
        return {"ok": True, "message": "swapped", "frozen": True}

    monkeypatch.setattr(updater, "apply", fake_apply)
    # Would raise / return the git error if the frozen branch were missing.
    r = asyncio.run(upstream.sync_source("self"))
    assert called.get("yes") is True
    assert r["ok"] is True and r.get("frozen") is True


def test_sync_self_dev_still_git(monkeypatch):
    """Non-frozen (dev git checkout) keeps the git-pull path."""
    from app.services import updater

    monkeypatch.setattr(updater, "is_frozen", lambda: False)
    monkeypatch.setattr(upstream, "current_version", lambda spec: {
        "sha": "", "short": "", "source": "unknown", "dirty": False,
    })
    r = asyncio.run(upstream.sync_source("self"))
    assert r["ok"] is False
    assert "git checkout" in r["message"]


# ---------------- back-compat shims ----------------

def test_legacy_check_still_works(monkeypatch):
    """upstream.check() preserves legacy single-source shape for existing JS."""
    monkeypatch.setattr(upstream, "current_version", lambda spec: {
        "sha": "a" * 40, "short": "a" * 7, "source": "git", "dirty": False,
    })
    monkeypatch.setattr(upstream, "latest_remote", lambda spec: {
        "sha": "b" * 40, "short": "b" * 7, "message": "msg", "date": "", "url": "",
    })
    r = asyncio.run(upstream.check())
    assert "available" in r and "current" in r and "remote" in r
    assert r["available"] is True
