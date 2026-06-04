"""Integration-ish smoke tests for FastAPI endpoints.

We isolate the config file per test and mock out any service that touches
the network / Google / browser / LLM. No real app/data/config.json is ever
written because CONFIG_PATH points at tmp_path.
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app import config as appconfig
from app import main as app_main
from app.services import (cathlab_service, updater, sheet_service,
                          format_check_service, finalize_service)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(appconfig, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(appconfig, "_cached", None)
    # Sheet reset_cache is called in /api/settings — make it a no-op that
    # also doesn't depend on gspread being configured.
    monkeypatch.setattr(sheet_service, "reset_cache", lambda: None)
    return TestClient(app_main.app)


# ---------------- Page routes ----------------

def test_home_redirects_when_unconfigured(client):
    # Fresh config → is_ready() False → should redirect to /settings
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].endswith("/settings")


def test_home_renders_when_configured(client, tmp_path, monkeypatch):
    # Fill minimum fields so is_ready() passes
    creds_file = tmp_path / "creds.json"
    creds_file.write_text("{}", encoding="utf-8")
    appconfig.update(
        llm_provider="gemini", llm_api_key="AIzaXXX",
        google_creds_path=str(creds_file), sheet_id="FAKE_ID",
    )
    r = client.get("/")
    assert r.status_code == 200
    # index.html template should mention 入院
    assert "入院" in r.text or "admission" in r.text.lower()


def test_settings_page_renders(client):
    r = client.get("/settings")
    assert r.status_code == 200
    # Form should include provider input
    assert "llm_provider" in r.text or "設定" in r.text


# ---------------- /api/settings POST ----------------

def test_save_settings_ok(client):
    r = client.post("/api/settings", data={
        "llm_provider": "anthropic",
        "llm_api_key": "sk-ant-xxx",
        "llm_model": "",
        "google_creds_path": "/tmp/x.json",
        "sheet_id": "ABC123",
    })
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    cfg = appconfig.load()
    assert cfg.llm_provider == "anthropic"
    assert cfg.llm_api_key == "sk-ant-xxx"
    assert cfg.sheet_id == "ABC123"


def test_save_settings_blank_api_key_preserves_existing(client):
    # First save with a key
    client.post("/api/settings", data={
        "llm_provider": "openai",
        "llm_api_key": "sk-original",
        "google_creds_path": "/tmp/a.json",
        "sheet_id": "XID",
    })
    # Second save with blank key — should NOT wipe
    r = client.post("/api/settings", data={
        "llm_provider": "openai",
        "llm_api_key": "",          # blank
        "google_creds_path": "/tmp/a.json",
        "sheet_id": "XID",
    })
    assert r.status_code == 200
    cfg = appconfig.load()
    assert cfg.llm_api_key == "sk-original"


def test_save_settings_trims_whitespace(client):
    r = client.post("/api/settings", data={
        "llm_provider": "  gemini  ",
        "llm_api_key": "  AIzaXXX  ",
        "google_creds_path": "  /tmp/x.json  ",
        "sheet_id": "  ABC  ",
    })
    assert r.status_code == 200
    cfg = appconfig.load()
    assert cfg.llm_provider == "gemini"
    assert cfg.llm_api_key == "AIzaXXX"
    assert cfg.sheet_id == "ABC"


# ---------------- /api/update/check ----------------

def test_bug_report_save_bundles_images_into_zip(client, tmp_path, monkeypatch):
    """POST /api/bug-report/save with screenshots → a .zip under bug_reports."""
    import zipfile
    from app.services import bug_report
    monkeypatch.setattr(appconfig, "DATA_DIR", tmp_path)
    r = client.post("/api/bug-report/save",
                     data={"note": "n", "step": "s", "error": "e"},
                     files=[("images", ("a.png", b"img1", "image/png")),
                            ("images", ("b.jpg", b"img2", "image/jpeg"))])
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["images"] == 2
    p = tmp_path / "bug_reports"
    zips = list(p.glob("*.zip"))
    assert len(zips) == 1
    with zipfile.ZipFile(zips[0]) as zf:
        assert "report.txt" in zf.namelist()
        assert sum(n.startswith("screenshot_") for n in zf.namelist()) == 2


def test_bug_report_save_without_images_is_plain_txt(client, tmp_path, monkeypatch):
    monkeypatch.setattr(appconfig, "DATA_DIR", tmp_path)
    r = client.post("/api/bug-report/save",
                     data={"note": "n", "step": "s", "error": "e"})
    assert r.status_code == 200
    assert r.json()["images"] == 0
    assert list((tmp_path / "bug_reports").glob("*.txt"))


def test_sheet_delete_rejects_non_date_tabs(client, monkeypatch):
    """Batch-delete refuses any tab name that isn't exactly YYYYMMDD —
    config tabs (主治醫師抽籤表 …) can never be deleted."""
    import json as _json
    deleted: list = []

    class FakeWS:
        def __init__(self, title): self.title = title

    class FakeSH:
        def __init__(self):
            self._ws = [FakeWS("20260520"), FakeWS("20260521"),
                        FakeWS("主治醫師抽籤表")]
        def worksheets(self): return list(self._ws)
        def del_worksheet(self, ws):
            self._ws.remove(ws); deleted.append(ws.title)

    fake = FakeSH()
    monkeypatch.setattr(sheet_service, "get_spreadsheet", lambda: fake)

    r = client.post("/api/sheet/delete",
                     data={"names_json": _json.dumps(["主治醫師抽籤表"])})
    assert r.status_code == 400
    assert deleted == []

    r = client.post("/api/sheet/delete",
                     data={"names_json": _json.dumps(["20260520", "20260521"])})
    assert r.status_code == 200
    body = r.json()
    assert sorted(body["deleted"]) == ["20260520", "20260521"]
    assert body["failed"] == []
    assert sorted(deleted) == ["20260520", "20260521"]


def test_sheet_delete_keeps_last_worksheet(client, monkeypatch):
    """A spreadsheet must keep ≥1 worksheet — the last one is never deleted."""
    import json as _json

    class FakeWS:
        def __init__(self, title): self.title = title

    class FakeSH:
        def __init__(self): self._ws = [FakeWS("20260520")]
        def worksheets(self): return list(self._ws)
        def del_worksheet(self, ws): self._ws.remove(ws)

    monkeypatch.setattr(sheet_service, "get_spreadsheet", lambda: FakeSH())
    r = client.post("/api/sheet/delete",
                     data={"names_json": _json.dumps(["20260520"])})
    assert r.status_code == 200
    body = r.json()
    assert body["deleted"] == []
    assert body["failed"][0]["name"] == "20260520"


def test_update_check_routes_through_updater(client, monkeypatch):
    async def fake_check():
        return {"available": True, "current": {"short": "aaa"},
                "remote": {"short": "bbb"}, "repo_url": "https://x"}
    monkeypatch.setattr(updater, "check", fake_check)

    r = client.get("/api/update/check")
    assert r.status_code == 200
    data = r.json()
    assert data["available"] is True
    assert data["remote"]["short"] == "bbb"


def test_update_apply_non_git_message(client, monkeypatch):
    # current_version returns source=file → apply() returns ok=False
    monkeypatch.setattr(updater, "current_version", lambda: {
        "sha": "x", "short": "x", "source": "file", "dirty": False,
    })
    r = client.post("/api/update/apply", data={"restart": "no"})
    assert r.status_code == 200
    assert r.json()["ok"] is False


# ---------------- /api/step5/plan ----------------

def test_step5_plan_routes_through_cathlab_service(client, monkeypatch):
    # Avoid hitting the real Sheet by stubbing read_patients
    monkeypatch.setattr(cathlab_service, "read_patients",
                        lambda d: [{"seq": 1, "doctor": "詹世鴻",
                                    "name": "王小明", "chart": "12345678",
                                    "diag": "CAD", "cath": "Left heart cath.",
                                    "note": "", "skip": False}])
    r = client.get("/api/step5/plan", params={"date": "20260410"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    # plan keyed by cath_date
    assert "2026/04/10" in data["plan"]
    entry = data["plan"]["2026/04/10"][0]
    assert entry["session"] == "AM"
    assert entry["room"] == "C2"


# ---------------- /api/format/check & /api/format/fix ----------------

def test_format_check_routes_through_service(client, monkeypatch):
    monkeypatch.setattr(format_check_service, "check", lambda d: {
        "structure": {"main_end": 3, "subs": []},
        "issues": [{"type": "main_header_missing", "fixable": True}],
        "main_header": [], "order_header": [],
    })
    r = client.get("/api/format/check", params={"date": "20260420"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["issues"][0]["type"] == "main_header_missing"


def test_format_fix_passes_types_list(client, monkeypatch):
    seen = {}
    def fake_fix(date, types=None):
        seen["date"] = date
        seen["types"] = types
        return {"applied": [], "remaining_issues": [], "structure": {"main_end": 1, "subs": []}}
    monkeypatch.setattr(format_check_service, "fix", fake_fix)

    r = client.post("/api/format/fix",
                    data={"date": "20260420",
                          "types": "gap_too_small,subtable_count_mismatch"})
    assert r.status_code == 200
    assert seen["date"] == "20260420"
    assert seen["types"] == ["gap_too_small", "subtable_count_mismatch"]


def test_finalize_check_routes_through_service(client, monkeypatch):
    monkeypatch.setattr(finalize_service, "check_ready", lambda d: {
        "ready": False,
        "checks": [{"id": "format", "label": "L", "ok": True, "detail": ""},
                   {"id": "main_data", "label": "L", "ok": False, "detail": "第 2 列缺 姓名"}],
    })
    r = client.get("/api/finalize/check", params={"date": "20260420"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["ready"] is False
    assert len(data["checks"]) == 2


def test_format_fix_empty_types_means_all(client, monkeypatch):
    seen = {}
    def fake_fix(date, types=None):
        seen["types"] = types
        return {"applied": [], "remaining_issues": [], "structure": {"main_end": 1, "subs": []}}
    monkeypatch.setattr(format_check_service, "fix", fake_fix)
    r = client.post("/api/format/fix", data={"date": "20260420", "types": ""})
    assert r.status_code == 200
    assert seen["types"] is None


# ---------------- /api/sheet/list error propagation ----------------

def test_sheet_list_error_returns_500(client, monkeypatch):
    def boom():
        raise RuntimeError("no creds")
    monkeypatch.setattr(sheet_service, "list_sheets", boom)
    r = client.get("/api/sheet/list")
    assert r.status_code == 500
    assert "no creds" in r.text


# ---------------- /api/sheet/read ----------------

def test_sheet_read_missing_date_returns_400(client):
    r = client.get("/api/sheet/read?date=")
    assert r.status_code == 400


def test_sheet_read_missing_sheet_returns_error_payload(client, monkeypatch):
    monkeypatch.setattr(sheet_service, "get_worksheet", lambda name: None)
    r = client.get("/api/sheet/read?date=20260420")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "20260420" in body["error"]


def test_sheet_read_slices_main_ordering_subs(client, monkeypatch):
    # Synthesise rows: header + 2 main rows + 2 blank + sub-table for 李文煌(1)
    header_main  = ["實際住院日","開刀日","科別","主治醫師","主診斷(ICD)",
                    "姓名","性別","年齡","病歷號碼","病床號","入院提示","住急"]
    header_order = ["序號","主治醫師","病人姓名","備註(住服)","備註",
                    "病歷號","術前診斷","預計心導管"]
    row_main_1 = ["2026-04-20","","CV","李文煌","CAD","王小明","M","60","1234","A301","",""]
    row_main_2 = ["2026-04-20","","CV","劉秉彥","AS",  "張小華","F","70","5678","A302","",""]

    rows: list[list[str]] = [
        header_main + [""] + header_order,
        row_main_1 + [""] + ["1","李文煌","王小明","","","1234","CAD","PCI"],
        row_main_2 + [""] + ["2","劉秉彥","張小華","","","5678","AS", "TAVI"],
        [""] * 21,
        [""] * 21,
        ["李文煌（1人）"],
        ["姓名"],
        ["王小明","","","","1234","CAD","PCI"],
    ]

    class FakeWS:
        def get(self, a1):
            return rows

    monkeypatch.setattr(sheet_service, "get_worksheet", lambda name: FakeWS())
    r = client.get("/api/sheet/read?date=20260420")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["date"] == "20260420"
    # main_end should point at the last filled main-data row (row 3 = 1-indexed)
    assert body["main_end_row"] == 3
    assert len(body["main"]) == 3            # header + 2 data
    assert len(body["ordering"]) == 3        # same row range, columns N-U
    assert body["main"][1][5] == "王小明"
    assert body["ordering"][1][1] == "李文煌"
    assert len(body["subs"]) == 1
    assert body["subs"][0]["doctor"] == "李文煌"
    assert body["subs"][0]["declared"] == 1
    assert body["subs"][0]["actual_count"] == 1


def test_sheet_read_ordering_not_truncated_by_main(client, monkeypatch):
    """入院序 can be LONGER than main A-L — the trailing 序號 row must not
    be cut off by main_end (field bug 2026-05-21 #4/#5: main 9 / 入院序 10)."""
    header_main  = ["實際住院日","開刀日","科別","主治醫師","主診斷(ICD)",
                    "姓名","性別","年齡","病歷號碼","病床號","入院提示","住急"]
    header_order = ["序號","主治醫師","病人姓名","備註(住服)","備註",
                    "病歷號","術前診斷","預計心導管"]
    main_row = ["2026-05-24","","CV","Z","CAD","x","M","60","c","A","",""]
    blank12  = [""] * 12

    rows: list[list[str]] = [
        header_main + [""] + header_order,
        main_row + [""] + ["1","Z","甲","","","111","CAD","PCI"],
        main_row + [""] + ["2","Z","乙","","","222","AS","TAVI"],
        # main A-L blank here, but 入院序 still has 序號 3 → must NOT be dropped
        blank12  + [""] + ["3","Z","丙","","","333","CAD","PCI"],
    ]

    class FakeWS:
        def get(self, a1):
            return rows

    monkeypatch.setattr(sheet_service, "get_worksheet", lambda name: FakeWS())
    r = client.get("/api/sheet/read?date=20260524")
    assert r.status_code == 200
    body = r.json()
    assert body["main_end_row"] == 3          # main = header + 2 data rows
    assert len(body["main"]) == 3
    assert len(body["ordering"]) == 4         # header + 3 ordering rows
    assert body["ordering"][3][0] == "3"      # the trailing 序號 survives
    assert body["ordering"][3][2] == "丙"
