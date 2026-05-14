"""Pure-logic tests for cathlab_service. No Sheet / WEBCVIS needed."""
from __future__ import annotations

import pytest

from app.services import cathlab_service as cs


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


# ---------------- static data loads ----------------

def test_static_data_loadable():
    assert len(cs.doctor_codes()["doctors"]) >= 20
    assert "CAD" in cs.id_maps()["diag"]
    assert "Left heart cath." in cs.id_maps()["proc"]
    assert "詹世鴻" in cs.schedule()["doctors"]
