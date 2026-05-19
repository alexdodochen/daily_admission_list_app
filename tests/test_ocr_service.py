"""Tests for ocr_service — focus on the normalization step after LLM returns
JSON. Mocks the LLM so no real API call happens."""
from __future__ import annotations

import asyncio

import pytest

from app.services import ocr_service


class FakeLLM:
    """Stub LLM that always returns the configured payload for vision()."""
    def __init__(self, payload: str):
        self.payload = payload
        self.calls = 0

    async def vision(self, image_bytes, prompt, mime="image/png"):
        self.calls += 1
        return self.payload

    async def text(self, prompt, system=None):
        return ""


def _run(coro):
    return asyncio.run(coro)


def test_ocr_normalizes_all_12_keys(monkeypatch):
    # LLM gives back 1 full row + 1 partial row
    payload = """[
      {"admit_date": "2026/04/20", "op_date": "", "department": "心內",
       "doctor": "李文煌", "icd_diagnosis": "I25.10 CAD", "name": "王小明",
       "gender": "男", "age": 65, "chart_no": "12345678", "bed": "11A-01",
       "hint": "", "urgent": ""},
      {"name": "林大美", "chart_no": "99999999"}
    ]"""
    fake = FakeLLM(payload)
    monkeypatch.setattr(ocr_service, "get_llm", lambda: fake)

    out = _run(ocr_service.ocr_image(b"fakepng"))
    assert len(out) == 2
    # Row 0 — full
    assert out[0]["doctor"] == "李文煌"
    assert out[0]["age"] == "65"  # coerced to str
    assert out[0]["chart_no"] == "12345678"
    # Row 1 — partial, every missing key defaults to ""
    r1 = out[1]
    expected_keys = {"admit_date", "op_date", "department", "doctor",
                     "icd_diagnosis", "name", "gender", "age",
                     "chart_no", "bed", "hint", "urgent"}
    assert set(r1.keys()) == expected_keys
    assert r1["name"] == "林大美"
    assert r1["department"] == ""
    assert r1["doctor"] == ""


def test_ocr_strips_whitespace(monkeypatch):
    fake = FakeLLM('[{"name": "  王小明  ", "chart_no": " 12345 "}]')
    monkeypatch.setattr(ocr_service, "get_llm", lambda: fake)
    out = _run(ocr_service.ocr_image(b""))
    assert out[0]["name"] == "王小明"
    assert out[0]["chart_no"] == "12345"


def test_ocr_skips_non_dict_rows(monkeypatch):
    fake = FakeLLM('[{"name": "A"}, "garbage", 42, null, {"name": "B"}]')
    monkeypatch.setattr(ocr_service, "get_llm", lambda: fake)
    out = _run(ocr_service.ocr_image(b""))
    assert [r["name"] for r in out] == ["A", "B"]


def test_ocr_accepts_fenced_json(monkeypatch):
    fake = FakeLLM('```json\n[{"name": "甲"}]\n```')
    monkeypatch.setattr(ocr_service, "get_llm", lambda: fake)
    out = _run(ocr_service.ocr_image(b""))
    assert out == [{
        "admit_date": "", "op_date": "", "department": "", "doctor": "",
        "icd_diagnosis": "", "name": "甲", "gender": "", "age": "",
        "chart_no": "", "bed": "", "hint": "", "urgent": "",
    }]


def test_ocr_raises_when_not_list(monkeypatch):
    fake = FakeLLM('{"not": "a list"}')
    monkeypatch.setattr(ocr_service, "get_llm", lambda: fake)
    with pytest.raises(ValueError, match="陣列"):
        _run(ocr_service.ocr_image(b""))


def test_ocr_raises_on_total_garbage(monkeypatch):
    fake = FakeLLM("完全無法解析")
    monkeypatch.setattr(ocr_service, "get_llm", lambda: fake)
    with pytest.raises(ValueError):
        _run(ocr_service.ocr_image(b""))


# --------------------------- diff_main_data ---------------------------

def _ex(chart, name="", doctor=""):
    """Build a 12-col A-L row with chart_no at index 8."""
    return ["", "", "", doctor, "", name, "", "", chart, "", "", ""]


def _new(chart, name="", doctor=""):
    return {"chart_no": chart, "name": name, "doctor": doctor}


def test_diff_first_time_sheet_empty():
    d = ocr_service.diff_main_data([], [_new("111", "甲", "李文煌")])
    assert d["existing_count"] == 0
    assert d["new_count"] == 1
    assert len(d["added"]) == 1
    assert d["added"][0]["chart_no"] == "111"
    assert d["removed"] == [] and d["kept"] == []


def test_diff_all_kept_no_changes():
    existing = [_ex("111", "甲", "李文煌"), _ex("222", "乙", "柯呈諭")]
    new = [_new("111", "甲", "李文煌"), _new("222", "乙", "柯呈諭")]
    d = ocr_service.diff_main_data(existing, new)
    assert len(d["kept"]) == 2
    assert d["added"] == [] and d["removed"] == []
    assert d["doctor_changed"] == []


def test_diff_detects_added_and_removed():
    existing = [_ex("111", "甲"), _ex("222", "乙")]
    new = [_new("222", "乙"), _new("333", "丙")]
    d = ocr_service.diff_main_data(existing, new)
    assert [x["chart_no"] for x in d["added"]]   == ["333"]
    assert [x["chart_no"] for x in d["removed"]] == ["111"]
    assert [x["chart_no"] for x in d["kept"]]    == ["222"]


def test_diff_detects_doctor_change():
    existing = [_ex("111", "甲", "李文煌")]
    new = [_new("111", "甲", "柯呈諭")]
    d = ocr_service.diff_main_data(existing, new)
    assert d["kept"][0]["doctor_old"] == "李文煌"
    assert d["kept"][0]["doctor_new"] == "柯呈諭"
    assert d["doctor_changed"] == [
        {"chart_no": "111", "name": "甲", "old": "李文煌", "new": "柯呈諭"}
    ]


def test_diff_reports_unmatched_chartless_rows():
    # A row with name but no chart_no → unmatched (can't be diffed)
    existing = [["", "", "", "", "", "幽靈", "", "", "", "", "", ""]]
    new = [_new("", "無號新")]
    d = ocr_service.diff_main_data(existing, new)
    assert d["unmatched_existing"] == [0]
    assert d["unmatched_new"] == [0]


def test_diff_ignores_fully_blank_rows():
    existing = [_ex("111", "甲"), ["", "", "", "", "", "", "", "", "", "", "", ""]]
    new = [_new("111", "甲")]
    d = ocr_service.diff_main_data(existing, new)
    assert d["unmatched_existing"] == []
    assert len(d["kept"]) == 1


def test_plan_write_returns_first_time_shape_when_sheet_missing(monkeypatch):
    monkeypatch.setattr(ocr_service.sheet_service, "get_worksheet",
                        lambda name: None)
    r = ocr_service.plan_write("20260501", [_new("111", "甲")])
    assert r["sheet_has_data"] is False
    assert r["new_count"] == 1
    assert r["added"] == []  # added/removed only meaningful vs existing sheet


def test_write_to_sheet_refuses_overwrite_without_confirm(monkeypatch):
    """If sheet already has data and allow_overwrite=False → return diff, no write."""

    class FakeWS:
        id = 999

    fake_ws = FakeWS()
    write_calls = []
    monkeypatch.setattr(ocr_service.sheet_service, "ensure_date_sheet",
                        lambda d: fake_ws)
    monkeypatch.setattr(
        ocr_service.sheet_service, "read_range",
        lambda ws, a1: [_ex("111", "甲", "李文煌")],
    )
    monkeypatch.setattr(
        ocr_service.sheet_service, "write_range",
        lambda *a, **kw: write_calls.append((a, kw)),
    )
    r = ocr_service.write_to_sheet(
        "20260501", [_new("222", "乙", "柯呈諭")], allow_overwrite=False
    )
    assert r["needs_confirm"] is True
    assert len(r["added"]) == 1
    assert len(r["removed"]) == 1
    assert write_calls == []   # nothing written


def test_write_to_sheet_applies_when_confirmed(monkeypatch):
    class FakeWS:
        id = 999
    fake_ws = FakeWS()
    write_calls = []
    monkeypatch.setattr(ocr_service.sheet_service, "ensure_date_sheet",
                        lambda d: fake_ws)
    monkeypatch.setattr(
        ocr_service.sheet_service, "read_range",
        lambda ws, a1: [_ex("111", "甲")],
    )
    monkeypatch.setattr(
        ocr_service.sheet_service, "write_range",
        lambda ws, a1, body, raw=False: write_calls.append((a1, body)),
    )
    r = ocr_service.write_to_sheet(
        "20260501",
        [_new("222", "乙", "柯呈諭"), _new("333", "丙", "李文煌")],
        allow_overwrite=True,
    )
    assert r["needs_confirm"] is False
    assert r["rows"] == 2
    # write_range called for A2:L body, plus the sub-table refresh on diff
    assert any(c[0] == "A2:L3" for c in write_calls)


def test_reupload_no_membership_change_is_noop(monkeypatch):
    """Re-uploading a screenshot with the SAME patients → 照舊: write
    NOTHING (keyed A-L cells must survive verbatim)."""
    class FakeWS:
        id = 999
    fake_ws = FakeWS()
    write_calls, clear_calls = [], []
    monkeypatch.setattr(ocr_service.sheet_service, "ensure_date_sheet",
                        lambda d: fake_ws)
    monkeypatch.setattr(ocr_service.sheet_service, "ensure_chart_text_format",
                        lambda ws: None)
    # Existing row carries a user-keyed bed ("11A-01") OCR wouldn't know.
    keyed = ["", "", "", "李文煌", "", "甲", "", "", "111", "11A-01", "", ""]
    monkeypatch.setattr(ocr_service.sheet_service, "read_range",
                        lambda ws, a1: [keyed] if a1 == "A2:L200" else [])
    monkeypatch.setattr(ocr_service.sheet_service, "write_range",
                        lambda *a, **kw: write_calls.append(a))
    monkeypatch.setattr(ocr_service.sheet_service, "clear_range",
                        lambda *a, **kw: clear_calls.append(a))
    r = ocr_service.write_to_sheet(
        "20260501", [_new("111", "甲", "李文煌")], allow_overwrite=True,
    )
    assert r["unchanged"] is True
    assert write_calls == [] and clear_calls == []   # nothing touched


def test_reupload_keeps_kept_rows_verbatim_on_membership_change(monkeypatch):
    """Add + remove present → kept patient's A-L row is preserved EXACTLY
    (not re-OCR'd); removed dropped; added appended from OCR."""
    class FakeWS:
        id = 999
    fake_ws = FakeWS()
    written = {}
    monkeypatch.setattr(ocr_service.sheet_service, "ensure_date_sheet",
                        lambda d: fake_ws)
    monkeypatch.setattr(ocr_service.sheet_service, "ensure_chart_text_format",
                        lambda ws: None)
    keyed111 = ["2026-05-01", "", "CV", "李文煌", "I25.10", "甲", "M", "65",
                "111", "11A-01", "VIP", ""]
    monkeypatch.setattr(
        ocr_service.sheet_service, "read_range",
        lambda ws, a1: [keyed111] if a1 == "A2:L200" else [],
    )
    def fake_write(ws, a1, body, raw=False):
        written["a1"] = a1
        written["body"] = body
    monkeypatch.setattr(ocr_service.sheet_service, "write_range", fake_write)
    monkeypatch.setattr(ocr_service.sheet_service, "clear_range",
                        lambda *a, **kw: None)
    monkeypatch.setattr(ocr_service, "_apply_diff_to_subtables",
                        lambda *a, **kw: {"updated": False})
    r = ocr_service.write_to_sheet(
        "20260501",
        # 111 kept (but OCR now has DIFFERENT/blanker values), 999 added
        [_new("111", "甲", "李文煌"), _new("999", "丁", "柯呈諭")],
        allow_overwrite=True,
    )
    assert r.get("unchanged") is not True
    # Row 0 = the untouched keyed 111 row (bed 11A-01, VIP hint survive)
    assert written["body"][0] == keyed111
    # Row 1 = the appended new patient 999 (from OCR)
    assert written["body"][1][8] == "999"
    assert len(written["body"]) == 2


# --------------------- sub-table auto-update ---------------------

from app.services import format_check_service as _fcs  # noqa: E402


def _build_grid(main_rows: list[list[str]],
                subs: list[tuple[str, list[list[str]]]]) -> list[list[str]]:
    """
    Build an A1:H grid: header row + main rows (padded to 8 cols), 2 blank
    rows, then each sub-table as title row + subheader + patient rows + 2
    blank separator (except after the last).
    """
    grid: list[list[str]] = []
    grid.append(["實際住院日","開刀日","科別","主治醫師","主診斷(ICD)","姓名","性別","年齡"])
    for r in main_rows:
        grid.append((r + [""] * 8)[:8])
    grid.append([""] * 8)
    grid.append([""] * 8)
    for i, (doctor, patients) in enumerate(subs):
        grid.append([f"{doctor}（{len(patients)}人）", "", "", "", "", "", "", ""])
        grid.append(["姓名","病歷號","EMR","summary","入院序","術前診斷","預計心導管","註記"])
        for p in patients:
            grid.append((p + [""] * 8)[:8])
        if i < len(subs) - 1:
            grid.append([""] * 8)
            grid.append([""] * 8)
    return grid


class _FakeWS:
    id = 1


def test_subtable_sync_removes_cancelled_patient(monkeypatch):
    grid = _build_grid(
        main_rows=[
            ["2026-05-01","","CV","李文煌","CAD","甲","","",],
            ["2026-05-01","","CV","柯呈諭","AS", "乙","","",],
        ],
        subs=[
            ("李文煌", [["甲","111","","","","CAD","PCI",""]]),
            ("柯呈諭", [["乙","222","","","","AS","TAVI",""]]),
        ],
    )
    writes: list = []
    clears: list = []
    monkeypatch.setattr(ocr_service.sheet_service, "write_range",
                        lambda ws, a1, body, raw=False: writes.append((a1, body)))
    monkeypatch.setattr(ocr_service.sheet_service, "clear_range",
                        lambda ws, a1: clears.append(a1))

    diff = {
        "added": [],
        "removed": [{"chart_no": "111", "name": "甲", "doctor": "李文煌"}],
        "doctor_changed": [],
    }
    result = ocr_service._apply_diff_to_subtables(
        _FakeWS(), grid, diff, new_patients=[], fmt_svc=_fcs,
    )
    assert result["updated"] is True
    assert result["removed"] == ["111"]
    # Find the title row for 李文煌 in the written body — should now be 0 人
    a1, body = writes[-1]
    titles = [row[0] for row in body if "人）" in (row[0] or "")]
    assert "李文煌（0人）" in titles
    assert "柯呈諭（1人）" in titles


def test_subtable_sync_appends_added_patient_to_its_doctor(monkeypatch):
    grid = _build_grid(
        main_rows=[["2026-05-01","","CV","李文煌","CAD","甲","","",]],
        subs=[("李文煌", [["甲","111","","","","CAD","PCI",""]])],
    )
    writes: list = []
    monkeypatch.setattr(ocr_service.sheet_service, "write_range",
                        lambda ws, a1, body, raw=False: writes.append((a1, body)))
    monkeypatch.setattr(ocr_service.sheet_service, "clear_range",
                        lambda ws, a1: None)

    diff = {
        "added": [{"chart_no": "333", "name": "丙", "doctor": "李文煌"}],
        "removed": [],
        "doctor_changed": [],
    }
    new_patients = [_new("111", "甲", "李文煌"), _new("333", "丙", "李文煌")]
    result = ocr_service._apply_diff_to_subtables(
        _FakeWS(), grid, diff, new_patients=new_patients, fmt_svc=_fcs,
    )
    assert result["updated"] is True
    assert len(result["added"]) == 1
    a1, body = writes[-1]
    titles = [row[0] for row in body if "人）" in (row[0] or "")]
    assert "李文煌（2人）" in titles
    # The new patient row appears in body
    new_rows = [row for row in body if row[1] == "333"]
    assert len(new_rows) == 1
    assert new_rows[0][0] == "丙"


def test_subtable_sync_moves_doctor_changed_patient(monkeypatch):
    grid = _build_grid(
        main_rows=[
            ["2026-05-01","","CV","李文煌","CAD","甲","","",],
            ["2026-05-01","","CV","劉秉彥","AS", "乙","","",],
        ],
        subs=[
            ("李文煌", [["甲","111","","","2","CAD","PCI",""]]),
            ("劉秉彥", [["乙","222","","","","AS","TAVI",""]]),
        ],
    )
    writes: list = []
    monkeypatch.setattr(ocr_service.sheet_service, "write_range",
                        lambda ws, a1, body, raw=False: writes.append((a1, body)))
    monkeypatch.setattr(ocr_service.sheet_service, "clear_range",
                        lambda ws, a1: None)

    diff = {
        "added": [],
        "removed": [],
        "doctor_changed": [
            {"chart_no": "111", "name": "甲", "old": "李文煌", "new": "劉秉彥"},
        ],
    }
    result = ocr_service._apply_diff_to_subtables(
        _FakeWS(), grid, diff, new_patients=[_new("111", "甲", "劉秉彥")],
        fmt_svc=_fcs,
    )
    assert result["updated"] is True
    assert len(result["moved"]) == 1
    a1, body = writes[-1]
    titles = [row[0] for row in body if "人）" in (row[0] or "")]
    assert "李文煌（0人）" in titles
    assert "劉秉彥（2人）" in titles
    # E (入院序) should be cleared on move so it doesn't pollute new doctor
    moved_rows = [row for row in body if row[1] == "111"]
    assert len(moved_rows) == 1
    assert moved_rows[0][4] == ""   # was "2" before, cleared on move


def test_subtable_sync_autocreates_block_for_unknown_doctor(monkeypatch):
    """A patient whose doctor has no sub-table should trigger creation of a new
    sub-table block at the end (Item 3 / 2026-05-15)."""
    grid = _build_grid(
        main_rows=[["2026-05-01","","CV","李文煌","CAD","甲","","",]],
        subs=[("李文煌", [["甲","111","","","","CAD","PCI",""]])],
    )
    writes: list = []
    monkeypatch.setattr(ocr_service.sheet_service, "write_range",
                        lambda ws, a1, body, raw=False: writes.append((a1, body)))
    monkeypatch.setattr(ocr_service.sheet_service, "clear_range",
                        lambda ws, a1: None)

    diff = {
        "added": [{"chart_no": "999", "name": "戊", "doctor": "新醫師"}],
        "removed": [],
        "doctor_changed": [],
    }
    result = ocr_service._apply_diff_to_subtables(
        _FakeWS(), grid, diff,
        new_patients=[_new("999", "戊", "新醫師")], fmt_svc=_fcs,
    )
    assert result["unattached_added"] == []
    assert [a["chart_no"] for a in result["added"]] == ["999"]
    assert result["auto_created_doctors"] == ["新醫師"]
    a1, body = writes[-1]
    titles = [row[0] for row in body if "人）" in (row[0] or "")]
    assert "李文煌（1人）" in titles
    assert "新醫師（1人）" in titles
    # New doctor's row appears
    new_rows = [row for row in body if row[1] == "999"]
    assert len(new_rows) == 1
    assert new_rows[0][0] == "戊"


def test_subtable_sync_autocreates_block_for_doctor_change_target(monkeypatch):
    """doctor_changed where the new doctor doesn't yet have a sub-table should
    also auto-create one (Item 3 / 2026-05-15)."""
    grid = _build_grid(
        main_rows=[["2026-05-01","","CV","李文煌","CAD","甲","","",]],
        subs=[("李文煌", [["甲","111","","","2","CAD","PCI",""]])],
    )
    writes: list = []
    monkeypatch.setattr(ocr_service.sheet_service, "write_range",
                        lambda ws, a1, body, raw=False: writes.append((a1, body)))
    monkeypatch.setattr(ocr_service.sheet_service, "clear_range",
                        lambda ws, a1: None)

    diff = {
        "added": [],
        "removed": [],
        "doctor_changed": [
            {"chart_no": "111", "name": "甲", "old": "李文煌", "new": "新醫師"},
        ],
    }
    result = ocr_service._apply_diff_to_subtables(
        _FakeWS(), grid, diff,
        new_patients=[_new("111", "甲", "新醫師")], fmt_svc=_fcs,
    )
    assert result["unattached_changed"] == []
    assert [m["chart_no"] for m in result["moved"]] == ["111"]
    assert result["auto_created_doctors"] == ["新醫師"]
    a1, body = writes[-1]
    titles = [row[0] for row in body if "人）" in (row[0] or "")]
    assert "李文煌（0人）" in titles
    assert "新醫師（1人）" in titles


# --------------------- ordering sync on write_to_sheet ---------------------

def test_write_to_sheet_invokes_ordering_sync_after_diff(monkeypatch):
    """write_to_sheet should call ordering_service.sync_ordering_after_diff
    after a successful sub-table update so N-V stays consistent (Item 2)."""
    from app.services import ordering_service

    class FakeWS:
        id = 999
    fake_ws = FakeWS()
    monkeypatch.setattr(ocr_service.sheet_service, "ensure_date_sheet",
                        lambda d: fake_ws)
    # Pre-OCR sheet has 1 patient at chart 111
    pre_read = {
        "A2:L200":  [_ex("111", "甲", "李文煌")],
        "A1:H500":  [
            ["實際住院日","開刀日","科別","主治醫師","主診斷(ICD)","姓名","性別","年齡"],
            ["2026-05-01","","CV","李文煌","CAD","甲","","",],
            [""] * 8, [""] * 8,
            ["李文煌（1人）","","","","","","",""],
            ["姓名","病歷號","EMR","summary","入院序","術前診斷","預計心導管","註記"],
            ["甲","111","","","","CAD","PCI",""],
        ],
    }
    monkeypatch.setattr(
        ocr_service.sheet_service, "read_range",
        lambda ws, a1: pre_read.get(a1, []),
    )
    monkeypatch.setattr(ocr_service.sheet_service, "write_range",
                        lambda *a, **kw: None)
    monkeypatch.setattr(ocr_service.sheet_service, "clear_range",
                        lambda *a, **kw: None)

    called_with: list = []
    def fake_sync(date):
        called_with.append(date)
        return {"updated": True, "rows": 2, "range": "N2:V3",
                "added": [{"chart_no": "222"}], "removed": [], "doctor_changed": []}
    monkeypatch.setattr(ordering_service, "sync_ordering_after_diff", fake_sync)

    r = ocr_service.write_to_sheet(
        "20260501",
        [_new("111", "甲", "李文煌"), _new("222", "乙", "李文煌")],
        allow_overwrite=True,
    )
    assert called_with == ["20260501"]
    assert r["ordering_update"]["updated"] is True
    assert r["ordering_update"]["rows"] == 2
