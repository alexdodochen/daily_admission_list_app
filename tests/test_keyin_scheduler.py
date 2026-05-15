"""Pure-logic tests for keyin_scheduler.build_schedule_from_config.

The Playwright-driving SchedulerSession is not unit-tested — it needs a
live EDR session. These tests only cover the deterministic schedule builder.
"""
from __future__ import annotations

from datetime import date

from app.services.keyin_scheduler import build_schedule_from_config


def _base_cfg(**overrides):
    cfg = {
        "year": 2026, "month": 5,
        "vs_schedule": {},
        "cr_schedule": {},
        "tw_holidays": [],
        "waizhao_vs_list": [], "waizhao_r_list": [],
        "neizhao_vs_list": [], "neizhao_r_list": [],
        "icu_vs_list":     [], "icu_r_list":     [],
        "jiuzhen_r_list":  [],
    }
    cfg.update(overrides)
    return cfg


def test_vs_only_weekday_produces_4_shifts():
    """A weekday with only VS assigned → 4 VS night/oncall shifts."""
    # 2026-05-04 is Mon (weekday=0, non-holiday)
    cfg = _base_cfg(vs_schedule={"4": "廖瑀"}, test_from="4", test_to="4")
    schedule, is_holiday = build_schedule_from_config(cfg)
    assert is_holiday(date(2026, 5, 4)) is False
    # Weekday + only VS → 4 VS shifts (1, 9, 11, 15), no day rotation since
    # rotation lists are empty.
    docs = [(d, doc) for d, doc, _ in schedule]
    assert all(doc == "廖瑀" for _, doc in docs)
    shifts = sorted({sh for _, _, sh in schedule})
    assert shifts == ["11晚班照會VS", "15二級動員召回值班VS",
                      "1值班VS", "9急診白天照會VS"]


def test_holiday_vs_adds_white_day_consult():
    """Holiday with VS → 4 night shifts + 3 white-day consult shifts."""
    cfg = _base_cfg(
        vs_schedule={"1": "廖瑀"},  # 2026-05-01 is Fri + 勞動節
        tw_holidays=["2026-05-01"],
        test_from="1", test_to="1",
    )
    schedule, is_holiday = build_schedule_from_config(cfg)
    assert is_holiday(date(2026, 5, 1)) is True
    shifts = sorted({sh for _, _, sh in schedule})
    # 4 base VS + 3 holiday white-day VS = 7 distinct VS shifts
    assert "3科外白天照會VS" in shifts
    assert "5科內白天照會VS" in shifts
    assert "7ICU白天照會VS" in shifts
    assert "1值班VS" in shifts


def test_weekend_auto_detected_as_holiday():
    """Saturdays/Sundays are holidays even without tw_holidays entry."""
    cfg = _base_cfg(vs_schedule={"2": "廖瑀"})  # 2026-05-02 Sat
    _, is_holiday = build_schedule_from_config(cfg)
    assert is_holiday(date(2026, 5, 2)) is True   # Sat
    assert is_holiday(date(2026, 5, 3)) is True   # Sun


def test_weekday_rotation_advances_cursor():
    """waizhao_vs_list rotates across consecutive weekdays."""
    cfg = _base_cfg(
        waizhao_vs_list=["A", "B"],
        waizhao_vs_start=0,
        test_from="4", test_to="6",   # Mon-Wed (all weekdays)
    )
    schedule, _ = build_schedule_from_config(cfg)
    wai = [(d, doc) for d, doc, sh in schedule if sh == "3科外白天照會VS"]
    assert wai == [(4, "A"), (5, "B"), (6, "A")]


def test_test_range_limits_days():
    """test_from / test_to restrict the iterated range."""
    cfg = _base_cfg(
        vs_schedule={str(d): "X" for d in range(1, 32)},
        test_from="10", test_to="12",
    )
    schedule, _ = build_schedule_from_config(cfg)
    days = sorted({d for d, _, _ in schedule})
    assert days == [10, 11, 12]


def test_cr_holiday_includes_ccu_control_room():
    """Holiday CR doctor also gets the 13CCU shift (per upstream comment)."""
    cfg = _base_cfg(
        cr_schedule={"2": "胡展瀚"},   # 2026-05-02 Sat
        test_from="2", test_to="2",
    )
    schedule, _ = build_schedule_from_config(cfg)
    shifts = sorted({sh for _, _, sh in schedule})
    assert "13CCU白天控床CR" in shifts
    assert "10急診白天照會R" in shifts


def test_taiwan_holiday_string_parses():
    """tw_holidays accepts ISO date strings; is_holiday returns True for them."""
    cfg = _base_cfg(tw_holidays=["2026-05-05"])  # Tue normally
    _, is_holiday = build_schedule_from_config(cfg)
    assert is_holiday(date(2026, 5, 5)) is True
    assert is_holiday(date(2026, 5, 6)) is False
