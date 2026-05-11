"""Tests for the multi-source upstream module."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.services import upstream, sync_manifest


# ---------------- registry ----------------

def test_three_sources_present():
    assert set(upstream.SOURCES.keys()) == {"self", "admission", "schedule"}
    self_spec = upstream.SOURCES["self"]
    assert self_spec.name == "daily_admission_list_app"
    assert upstream.SOURCES["admission"].name == "daily-admission-list-public"
    assert upstream.SOURCES["schedule"].name == "Key-Schedule-APP"


def test_source_urls():
    a = upstream.SOURCES["admission"]
    assert a.html_url == "https://github.com/alexdodochen/daily-admission-list-public"
    assert a.api_base == "https://api.github.com/repos/alexdodochen/daily-admission-list-public"
    assert a.clone_url == "https://github.com/alexdodochen/daily-admission-list-public.git"


def test_manifest_has_admission_and_schedule():
    assert "admission" in sync_manifest.MANIFEST
    assert "schedule" in sync_manifest.MANIFEST
    # admission has at least cathlab_id_maps.json mirror rule
    auto = sync_manifest.MANIFEST["admission"]["auto_mirror"]
    assert any("cathlab_id_maps.json" in src for src, _ in auto)
    # schedule has needs_port entries pointing to scheduler/keyin services
    np = sync_manifest.MANIFEST["schedule"]["needs_port"]
    assert any("cv_solver" in row[0] for row in np)
    assert any("keyin" in row[0] for row in np)


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


def test_current_version_upstream_uncloned(monkeypatch, tmp_path):
    # Force EXTERNAL_DIR somewhere fresh so the upstream isn't cloned there
    monkeypatch.setattr(upstream, "EXTERNAL_DIR", tmp_path / "external")
    (tmp_path / "external").mkdir()
    # repo_path() reads EXTERNAL_DIR via spec name
    spec = upstream.SOURCES["admission"]
    # Make sure no .git exists at that path
    cur = upstream.current_version(spec)
    assert cur["source"] == "uncloned"


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


def test_check_source_uncloned_treated_as_update(monkeypatch):
    monkeypatch.setattr(upstream, "current_version", lambda spec: {
        "sha": "", "short": "", "source": "uncloned", "dirty": False,
    })
    monkeypatch.setattr(upstream, "latest_remote", lambda spec: {
        "sha": "abc" + "0" * 37, "short": "abc0000",
        "message": "feat", "date": "", "url": "",
    })
    monkeypatch.setattr(upstream, "commits_between",
                        lambda *a, **kw: [])
    monkeypatch.setattr(upstream, "sync_state", lambda: {})
    r = asyncio.run(upstream.check_source("admission"))
    assert r["available"] is True
    assert r["current"]["source"] == "uncloned"


def test_check_source_network_error(monkeypatch):
    monkeypatch.setattr(upstream, "current_version", lambda spec: {
        "sha": "x", "short": "x", "source": "git", "dirty": False,
    })
    def boom(spec):
        raise RuntimeError("offline")
    monkeypatch.setattr(upstream, "latest_remote", boom)
    monkeypatch.setattr(upstream, "sync_state", lambda: {})
    r = asyncio.run(upstream.check_source("schedule"))
    assert r["available"] is False
    assert "offline" in r["error"]


# ---------------- check_all ----------------

def test_check_all_returns_three_keys(monkeypatch):
    monkeypatch.setattr(upstream, "current_version", lambda spec: {
        "sha": "x" * 40, "short": "x" * 7, "source": "git", "dirty": False,
    })
    monkeypatch.setattr(upstream, "latest_remote", lambda spec: {
        "sha": "x" * 40, "short": "x" * 7, "message": "", "date": "", "url": "",
    })
    monkeypatch.setattr(upstream, "sync_state", lambda: {})
    out = asyncio.run(upstream.check_all())
    assert set(out.keys()) == {"self", "admission", "schedule"}
    for v in out.values():
        assert v["available"] is False


# ---------------- sync_state read/write ----------------

def test_sync_state_roundtrip(tmp_path, monkeypatch):
    state_path = tmp_path / "integration_state.json"
    monkeypatch.setattr(upstream, "STATE_PATH", state_path)
    assert upstream.sync_state() == {}
    upstream._record_sync("admission", "abc1234", ["data/static/x.json"])
    on_disk = json.loads(state_path.read_text(encoding="utf-8"))
    assert on_disk["admission"]["sha"] == "abc1234"
    assert "synced_at" in on_disk["admission"]
    assert on_disk["admission"]["mirrored"] == ["data/static/x.json"]


# ---------------- mirror logic ----------------

def test_run_mirror_copies_whitelisted_files(tmp_path, monkeypatch):
    """_run_mirror should copy upstream files to DATA_DIR per manifest."""
    fake_clone = tmp_path / "external" / "daily-admission-list-public"
    fake_clone.mkdir(parents=True)
    (fake_clone / "cathlab_id_maps.json").write_text('{"diag": {}}', encoding="utf-8")
    (fake_clone / "schedule_readable.txt").write_text("hello", encoding="utf-8")

    fake_data = tmp_path / "data"
    fake_data.mkdir()
    monkeypatch.setattr(upstream, "DATA_DIR", fake_data)
    monkeypatch.setattr(upstream, "STATIC_DEST_ROOT", fake_data / "static")

    spec = upstream.SOURCES["admission"]
    mirrored, errors = upstream._run_mirror(spec, fake_clone)

    assert len(errors) == 0
    assert (fake_data / "static" / "cathlab_id_maps.json").exists()
    assert (fake_data / "static" / "schedule_readable.txt").exists()
    assert any("cathlab_id_maps.json" in p for p in mirrored)


def test_run_mirror_records_missing_upstream_files(tmp_path, monkeypatch):
    fake_clone = tmp_path / "external" / "daily-admission-list-public"
    fake_clone.mkdir(parents=True)
    # cathlab_id_maps.json is missing → should be reported as error
    fake_data = tmp_path / "data"
    fake_data.mkdir()
    monkeypatch.setattr(upstream, "DATA_DIR", fake_data)
    monkeypatch.setattr(upstream, "STATIC_DEST_ROOT", fake_data / "static")

    spec = upstream.SOURCES["admission"]
    mirrored, errors = upstream._run_mirror(spec, fake_clone)
    assert mirrored == []
    assert any("cathlab_id_maps.json" in e["src"] for e in errors)


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
