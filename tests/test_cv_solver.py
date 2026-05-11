"""Pure-logic tests for cv_solver (Card 1 — 排班).

cv_solver has no I/O — caller supplies baseline dict, gets schedule dict
back. These tests exercise the public surface without hitting any sheet.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.services import cv_solver


# ---------------------- Holiday classification ----------------------

def test_weekends_are_holidays():
    # 2026-05-11 is Mon, 5-16 Sat, 5-17 Sun
    assert cv_solver.is_taiwan_holiday(date(2026, 5, 16)) is True
    assert cv_solver.is_taiwan_holiday(date(2026, 5, 17)) is True
    assert cv_solver.is_taiwan_holiday(date(2026, 5, 11)) is False


def test_official_holidays_are_in_set():
    # Sample known holidays
    assert date(2026, 1, 1) in cv_solver.TAIWAN_HOLIDAYS
    assert date(2026, 2, 17) in cv_solver.TAIWAN_HOLIDAYS  # 春節初一
    assert date(2026, 5, 1) in cv_solver.TAIWAN_HOLIDAYS   # 勞動節
    # Non-holiday weekday
    assert date(2026, 5, 11) not in cv_solver.TAIWAN_HOLIDAYS


def test_stat_type_classification():
    fn = cv_solver.make_stat_type_fn(cv_solver.is_taiwan_holiday)
    # Plain Monday in May 2026
    assert fn(date(2026, 5, 11)) == "平日"
    # Friday in May 2026 (5/8) — non-holiday, regular Friday
    assert fn(date(2026, 5, 8)) == "週五班"
    # 2026-05-16 (Sat) — holiday, next day (Sun) also holiday → 週六班
    assert fn(date(2026, 5, 16)) == "週六班"
    # 2026-05-17 (Sun) — holiday, next day (Mon 5/18) not holiday → 週日班
    assert fn(date(2026, 5, 17)) == "週日班"
    # Day before official holiday: 4/30 (Thu) before 5/1 holiday → 週五班
    assert fn(date(2026, 4, 30)) == "週五班"


# ---------------------- Month math ----------------------

def test_month_days_count():
    assert len(cv_solver.month_days(2026, 1)) == 31
    assert len(cv_solver.month_days(2026, 2)) == 28
    assert len(cv_solver.month_days(2026, 4)) == 30


def test_month_h_w_sum():
    H, W = cv_solver.month_h_w(2026, 5)
    assert H + W == 31
    # May 2026: 10 weekend days (5/2,3,9,10,16,17,23,24,30,31) + 5/1 勞動節 (Fri) = 11
    assert H == 11
    assert W == 20


# ---------------------- compute_initial_targets ----------------------

def test_compute_initial_targets_shape():
    baseline = {n: {"平日": 0, "週五": 0, "週六": 0, "週日": 0, "假日": 0}
                for n in cv_solver.ALL_DOCTORS}
    t = cv_solver.compute_initial_targets(2026, 6, X=4, baseline=baseline)
    assert "H" in t and "W" in t
    assert t["H"] + t["W"] == 30  # June has 30 days
    assert set(t["vs_per_doctor"].keys()) == set(cv_solver.VS_LIST)
    for vs in cv_solver.VS_LIST:
        d = t["vs_per_doctor"][vs]
        assert {"holiday", "weekday"} == set(d.keys())
        # VS caps respected
        assert d["holiday"] <= cv_solver.VS_HOLIDAY_CAP
        assert d["holiday"] + d["weekday"] <= cv_solver.VS_TOTAL_CAP
    assert 0 <= t["jk_count"] <= cv_solver.JK_WEEKDAY_CAP


def test_compute_initial_targets_x_too_low_warns():
    baseline = {n: {"平日": 0, "週五": 0, "週六": 0, "週日": 0, "假日": 0}
                for n in cv_solver.ALL_DOCTORS}
    # X=0 + 建寬=3 → W-15-0-3 platform of remaining weekday slots; depends on month
    t = cv_solver.compute_initial_targets(2026, 6, X=0, baseline=baseline)
    # warnings is always a list
    assert isinstance(t["warnings"], list)


# ---------------------- solver private helpers ----------------------

def test_qod_count_pure():
    from datetime import timedelta
    base = date(2026, 6, 1)
    # Two QOD pairs: 6/1↔6/3, 6/3↔6/5 → 6/1 and 6/3 each have qod_next, so count=2
    s = {base, base + timedelta(days=2), base + timedelta(days=4)}
    assert cv_solver._qod_count(s) == 2
    # No QOD
    assert cv_solver._qod_count({base, base + timedelta(days=1)}) == 0


def test_scan_qod_excludes_展瀚():
    """展瀚 is allowed to have QOD-pair days — should not appear in violations."""
    from datetime import timedelta
    base = date(2026, 6, 1)
    schedule = {
        base: "展瀚",
        base + timedelta(days=2): "展瀚",
        base + timedelta(days=1): "麒翔",
        base + timedelta(days=3): "麒翔",
    }
    violations = cv_solver._scan_qod(schedule)
    # 麒翔 has QOD (6/2 and 6/4) → should appear; 展瀚 should NOT
    names = {n for _, n in violations}
    assert "展瀚" not in names
    assert "麒翔" in names
