"""Endpoint shape tests for keyin_routes — uses FastAPI TestClient.
Heavy code paths (start/cancel/Playwright) are not exercised; we only check
that the routes are wired up correctly and return the expected JSON shape.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch, tmp_path):
    # Bypass settings gate so /keyin/ renders even on a fresh checkout.
    from app import config as appconfig
    monkeypatch.setattr(appconfig.AppConfig, "is_ready", lambda self: True)
    from app.main import app
    return TestClient(app)


def test_keyin_index_renders(client):
    r = client.get("/keyin/")
    assert r.status_code == 200
    assert "key 班" in r.text or "Key 班" in r.text


def test_keyin_status_idle_when_no_session(client):
    r = client.get("/keyin/api/status")
    assert r.status_code == 200
    data = r.json()
    assert data["state"] == "idle"
    assert data["logs"] == []


def test_keyin_prefill_empty_returns_ok_false(client):
    # Reset module-level slot first
    from app.services import keyin_routes
    keyin_routes.prefill_payload = None
    r = client.get("/keyin/api/prefill")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False


def test_keyin_prefill_consumes_once(client):
    from app.services import keyin_routes
    keyin_routes.prefill_payload = {"year": 2026, "month": 5,
                                    "vs_schedule": {"1": "廖瑀"},
                                    "cr_schedule": {}, "tw_holidays": []}
    r1 = client.get("/keyin/api/prefill")
    assert r1.json()["ok"] is True
    assert r1.json()["prefill"]["year"] == 2026
    # Second call should find empty slot
    r2 = client.get("/keyin/api/prefill")
    assert r2.json()["ok"] is False


def test_keyin_preview_returns_schedule(client):
    body = {
        "year": 2026, "month": 5,
        "vs_schedule": {"4": "廖瑀"},   # Mon
        "cr_schedule": {},
        "tw_holidays": [],
        "test_from": "4", "test_to": "4",
    }
    r = client.post("/keyin/api/preview", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["total"] == 4   # weekday VS-only → 4 night/oncall shifts
    assert all(item["doctor"] == "廖瑀" for item in data["preview"])


def test_keyin_upload_rejects_bad_extension(client):
    r = client.post("/keyin/api/upload-schedule",
                    files={"file": ("test.csv", b"not excel", "text/csv")})
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert ".xls" in r.json()["error"]


def test_home_card_2_now_links_to_keyin(client):
    r = client.get("/")
    assert r.status_code == 200
    assert 'href="/keyin"' in r.text
    # The old "即將推出" badge should be gone
    assert "即將推出" not in r.text
