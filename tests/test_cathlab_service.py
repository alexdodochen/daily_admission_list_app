"""Pure-logic tests for cathlab_service. No Sheet / WEBCVIS needed."""
from __future__ import annotations

import pytest

from app import config as appconfig
from app.services import cathlab_service as cs


@pytest.fixture(autouse=True)
def _reset_cathlab_static_cache():
    """The static-dir + parsed-table caches are module globals; tests that
    monkeypatch DATA_DIR / drop temp files would otherwise leak a stale
    cached dir into later tests (incl. other files). Reset around each."""
    cs.reset_cache()
    yield
    cs.reset_cache()


# ---------------- get_cathlab_date ----------------

def test_friday_admission_same_day():
    # 2026-04-10 is Friday
    assert cs.get_cathlab_date("20260410", "任何醫師", "") == "2026/04/10"


def test_monday_admission_plus_one():
    # 2026-04-13 is Monday
    assert cs.get_cathlab_date("20260413", "詹世鴻", "") == "2026/04/14"


def test_tuesday_zhang_solo_same_day():
    # 2026-04-14 is Tuesday; 張獻元 solo (no 王思翰/張倉惟 in note)
    assert cs.get_cathlab_date("20260414", "張獻元", "") == "2026/04/14"


def test_tuesday_zhang_borrowed_plus_one():
    assert cs.get_cathlab_date("20260414", "張獻元", "王思翰借") == "2026/04/15"


def test_tuesday_other_doctor_plus_one():
    # Tuesday for non-張獻元 → N+1
    assert cs.get_cathlab_date("20260414", "陳儒逸", "") == "2026/04/15"


# ---------------- compute_slot ----------------

def test_scheduled_doctor_on_scheduled_day():
    slot = cs.compute_slot("詹世鴻", "2026/04/10")  # Fri
    assert slot["in_schedule"] is True
    assert slot["session"] == "AM"
    assert slot["room"] == "C2"


def test_unknown_doctor_is_off_schedule():
    slot = cs.compute_slot("測試醫師", "2026/04/13")
    assert slot["in_schedule"] is False
    assert slot["session"] == "OFF"
    assert slot["room"] == "H1"


def test_scheduled_doctor_off_day_is_off():
    # 許志新 only schedules Mon/Thu (0,3)
    slot = cs.compute_slot("許志新", "2026/04/14")  # Tue
    assert slot["in_schedule"] is False


def test_multi_slot_doctor_default_is_am():
    # 柯呈諭 Thu has AM C2 + PM C2 — default picks AM (first in list)
    slot = cs.compute_slot("柯呈諭", "2026/04/16")  # Thu
    assert slot["session"] == "AM"
    assert slot["room"] == "C2"


def test_multi_slot_doctor_prefer_pm():
    slot = cs.compute_slot("柯呈諭", "2026/04/16", prefer_session="PM")
    assert slot["session"] == "PM"


def test_compute_all_slots_returns_list():
    slots = cs.compute_all_slots("柯呈諭", "2026/04/16")
    assert len(slots) == 2
    assert {s["session"] for s in slots} == {"AM", "PM"}


def test_compute_all_slots_empty_for_unknown():
    assert cs.compute_all_slots("測試醫師", "2026/04/16") == []


def test_compute_all_slots_invalid_date():
    assert cs.compute_all_slots("柯呈諭", "not-a-date") == []


# ---------------- compute_time ----------------

def test_am_time_starts_0600():
    assert cs.compute_time("AM", 0) == "0600"
    assert cs.compute_time("AM", 5) == "0605"
    assert cs.compute_time("AM", 60) == "0700"


def test_pm_time_starts_1800():
    assert cs.compute_time("PM", 0) == "1800"


def test_off_time_starts_2100():
    assert cs.compute_time("OFF", 0) == "2100"


def test_unknown_session_defaults_off():
    assert cs.compute_time("XX", 0) == "2100"


# ---------------- resolve_diag / resolve_proc ----------------

def test_resolve_diag_exact():
    label, idv = cs.resolve_diag("CAD")
    assert label == "CAD"
    assert idv == "PDI20090908120009"


def test_resolve_diag_after_gt():
    # "EP study/RFA > pAf" → should pick "pAf"
    label, idv = cs.resolve_diag("EP study/RFA > pAf")
    assert label == "pAf"
    assert idv == "PDI20090908120040"


def test_resolve_diag_unknown_falls_back_to_others_pdi():
    # Per feedback_others_diag_freetext.md: any non-empty diag falls back to
    # OTHERS_PDI with an "Others:<text>" label so user-typed free text still
    # reaches WEBCVIS (under the OTHERS dropdown).
    label, idv = cs.resolve_diag("阿嬤 的 感冒")
    assert idv == cs.OTHERS_PDI
    assert label == "Others:阿嬤 的 感冒"


def test_resolve_diag_empty():
    assert cs.resolve_diag("") == ("", "")
    assert cs.resolve_diag("   ") == ("", "")


def test_resolve_proc_exact():
    label, idv = cs.resolve_proc("Left heart cath.")
    assert idv == "PHC20090907120001"


def test_resolve_proc_empty():
    assert cs.resolve_proc("") == ("", "")


# ---------------- _pick_second_doctor ----------------

def test_second_doctor_single_tag():
    full, tag = cs._pick_second_doctor("浩")
    assert full == "葉立浩"
    assert tag == "浩"


def test_second_doctor_priority_yeh():
    # 葉立浩 wins even if 寬 appears first in string
    full, _ = cs._pick_second_doctor("寬、浩")
    assert full == "葉立浩"


def test_second_doctor_single_non_priority():
    full, _ = cs._pick_second_doctor("嘉")
    assert full == "蘇奕嘉"


def test_second_doctor_none():
    assert cs._pick_second_doctor("") == ("", "")
    assert cs._pick_second_doctor("一般備註") == ("", "")


# ---------------- note_means_skip (備註 skip rules) ----------------

def test_note_skip_empty():
    assert cs.note_means_skip("") is False
    assert cs.note_means_skip("   ") is False


def test_note_skip_legacy_buchaicheng():
    """Original keyword 不排程 still works."""
    assert cs.note_means_skip("不排程") is True


def test_note_skip_buchaidaoguan():
    """The exact phrase the UI placeholder suggests: 不排導管."""
    assert cs.note_means_skip("不排導管") is True
    assert cs.note_means_skip("家屬決定不排導管") is True


def test_note_skip_buchai_with_cath():
    """English-mixed: 不排 cath."""
    assert cs.note_means_skip("不排 cath") is True
    assert cs.note_means_skip("不排cath") is True


def test_note_skip_buzuo_variants():
    """不做導管 / 不做 cath should also skip."""
    assert cs.note_means_skip("不做導管") is True
    assert cs.note_means_skip("不做 cath") is True


def test_note_skip_cancel_and_check():
    assert cs.note_means_skip("取消導管") is True
    assert cs.note_means_skip("檢查") is True
    assert cs.note_means_skip("檢查腎功能") is True


def test_note_skip_false_positive_buchaichu():
    """不排除做導管 = won't rule out cath; must NOT skip."""
    assert cs.note_means_skip("不排除做導管") is False
    assert cs.note_means_skip("不排除 PCI") is False


def test_note_skip_normal_text_does_not_skip():
    assert cs.note_means_skip("待會診") is False
    assert cs.note_means_skip("葉立浩 second") is False
    assert cs.note_means_skip("已 consent") is False


# ---------------- 主治醫師導管時段表 cell parser ----------------

def test_parse_schedule_cell_empty():
    assert cs._parse_schedule_cell("") is None
    assert cs._parse_schedule_cell("   ") is None


def test_parse_schedule_cell_plain_name():
    out = cs._parse_schedule_cell("陳柏升")
    assert out == {"name": "陳柏升", "tags": []}


def test_parse_schedule_cell_single_tag():
    out = cs._parse_schedule_cell("詹世鴻(軨)")
    assert out == {"name": "詹世鴻", "tags": ["軨"]}


def test_parse_schedule_cell_multi_tag():
    out = cs._parse_schedule_cell("黃鼎鈞(浩、晨)")
    assert out == {"name": "黃鼎鈞", "tags": ["浩", "晨"]}


def test_parse_schedule_cell_multiple_paren_groups():
    out = cs._parse_schedule_cell("EP(李柏增)(晨)")
    assert out == {"name": "EP", "tags": ["李柏增", "晨"]}


def test_parse_schedule_cell_continuation_no_primary():
    """Cells like '(陳則瑋)' have no primary name — overlay ignores them."""
    assert cs._parse_schedule_cell("(陳則瑋)") is None


# ---------------- _build_schedule_overlay_from_grid ----------------

def _make_grid(cells: dict) -> list[list[str]]:
    """Build a 15×7 grid from {(row_idx, col_idx): "text"}."""
    grid = [["" for _ in range(7)] for _ in range(15)]
    for (r, c), v in cells.items():
        grid[r][c] = v
    return grid


def test_overlay_zhan_shihong_wed_yu_lin(monkeypatch):
    """The user's actual case: 詹世鴻 on 週三 (Wed) → second = 許毓軨.
    Wed col idx = 4 (Mon=2, Tue=3, Wed=4, Thu=5, Fri=6).
    AM H1 primary row idx = 1.
    """
    grid = _make_grid({(1, 4): "詹世鴻(軨)"})
    overlay = cs._build_schedule_overlay_from_grid(grid)
    assert overlay.get("詹世鴻", {}).get("2") == {"second": "許毓軨"}


def test_overlay_huang_dingjun_with_two_tags():
    """黃鼎鈞 週四 (Thu, idx=5) AM C1 (row idx 5) → second=葉立浩, third=洪晨惠."""
    grid = _make_grid({(5, 5): "黃鼎鈞(浩、晨)"})
    overlay = cs._build_schedule_overlay_from_grid(grid)
    assert overlay.get("黃鼎鈞", {}).get("3") == {
        "second": "葉立浩", "third": "洪晨惠",
    }


def test_overlay_plain_name_no_entry():
    """Cells without tags don't add second/third (no point storing empty)."""
    grid = _make_grid({(1, 2): "陳柏升"})  # Mon AM H1
    overlay = cs._build_schedule_overlay_from_grid(grid)
    assert "陳柏升" not in overlay


def test_overlay_continuation_row_collected(monkeypatch):
    """Cont row (idx 2, parent idx 1) on Mon picks up a doctor too.
    Layout: cont rows 2,3 belong to primary idx 1 (H1 spans 2-4 in 1-indexed).
    """
    # Primary at idx 1 has "陳A", continuation at idx 2 has "陳B(浩)"
    grid = _make_grid({
        (1, 2): "陳A",
        (2, 2): "陳B(浩)",
    })
    overlay = cs._build_schedule_overlay_from_grid(grid)
    assert overlay.get("陳B", {}).get("0") == {"second": "葉立浩"}


def test_lookup_schedule_doctors_empty_when_no_overlay(monkeypatch):
    monkeypatch.setattr(cs, "_schedule_overlay", {})
    assert cs.lookup_schedule_doctors("詹世鴻", "2026/05/27") == {"second": "", "third": ""}


def test_lookup_schedule_doctors_returns_match(monkeypatch):
    """End-to-end: overlay → lookup_schedule_doctors picks the right (doc, wd)."""
    monkeypatch.setattr(cs, "_schedule_overlay", {
        "詹世鴻": {"2": {"second": "許毓軨"}},
    })
    out = cs.lookup_schedule_doctors("詹世鴻", "2026/05/27")  # 2026-05-27 = Wed
    assert out == {"second": "許毓軨", "third": ""}


def test_lookup_schedule_doctors_invalid_date(monkeypatch):
    assert cs.lookup_schedule_doctors("X", "bad-date") == {"second": "", "third": ""}


def test_read_schedule_overlay_missing_worksheet(monkeypatch):
    """No 主治醫師導管時段表 worksheet → empty overlay, no crash."""
    from app.services import sheet_service
    monkeypatch.setattr(cs, "_schedule_overlay", None)
    monkeypatch.setattr(sheet_service, "get_worksheet", lambda name: None)
    assert cs.read_schedule_overlay() == {}


def test_read_schedule_overlay_reads_grid(monkeypatch):
    """Worksheet present → grid parsed into overlay."""
    from app.services import sheet_service
    monkeypatch.setattr(cs, "_schedule_overlay", None)
    monkeypatch.setattr(sheet_service, "get_worksheet", lambda name: object())  # truthy
    monkeypatch.setattr(sheet_service, "read_range",
                        lambda ws, rng: _make_grid({(1, 4): "詹世鴻(軨)"}))
    out = cs.read_schedule_overlay()
    assert out.get("詹世鴻", {}).get("2") == {"second": "許毓軨"}


# ---------------- static data loads ----------------

def test_static_data_loadable():
    assert len(cs.doctor_codes()["doctors"]) >= 20
    assert "CAD" in cs.id_maps()["diag"]
    assert "Left heart cath." in cs.id_maps()["proc"]
    assert "詹世鴻" in cs.schedule()["doctors"]


def test_cathlab_static_status_present_in_dev():
    st = cs.cathlab_static_status()
    assert st["present"] is True
    # drop_dir is now DATA_DIR (same folder as service_account.json)
    assert st["drop_dir"] == str(appconfig.DATA_DIR)
    assert st["files"] == list(cs._STATIC_FILES)


def test_load_json_missing_raises_pointing_at_dropdir(tmp_path, monkeypatch):
    # Simulate the public CI build: resolved dir has no JSONs → the error
    # must tell the user exactly where to drop the 3 files (the same folder
    # as service_account.json) and mention all 3 filenames.
    monkeypatch.setattr(cs, "_static_dir", tmp_path)
    with pytest.raises(FileNotFoundError) as e:
        cs._load_json("cathlab_id_maps.json")
    msg = str(e.value)
    assert str(appconfig.DATA_DIR) in msg
    assert "service_account.json" in msg
    for fn in cs._STATIC_FILES:
        assert fn in msg


def test_loose_drop_into_data_dir_is_detected_and_migrated(tmp_path, monkeypatch):
    """The 3 JSONs dropped LOOSE into DATA_DIR (next to service_account.json)
    must resolve — and get normalised into DATA_DIR/cathlab_static so the
    next auto-update keeps them."""
    monkeypatch.setattr(appconfig, "DATA_DIR", tmp_path)
    cs.reset_cache()
    for fn in cs._STATIC_FILES:
        (tmp_path / fn).write_text("{}", encoding="utf-8")
    d = cs._resolve_static_dir()
    assert d == tmp_path / "cathlab_static"
    assert all((d / fn).is_file() for fn in cs._STATIC_FILES)


def test_reset_cache_picks_up_files_dropped_after_first_access(tmp_path, monkeypatch):
    """Stale-cache parity with the SA fix: files dropped AFTER first
    resolution are invisible until reset_cache()."""
    monkeypatch.setattr(appconfig, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cs, "STATIC_DIR", tmp_path / "nope")
    monkeypatch.setattr(appconfig, "APP_ROOT", tmp_path / "nope")
    cs.reset_cache()
    with pytest.raises(FileNotFoundError):
        cs._load_json("cathlab_id_maps.json")
    for fn in cs._STATIC_FILES:
        (tmp_path / fn).write_text("{}", encoding="utf-8")
    cs.reset_cache()
    assert cs._load_json("cathlab_id_maps.json") == {}
