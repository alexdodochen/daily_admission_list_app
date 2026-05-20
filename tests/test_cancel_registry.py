"""Pure-logic tests for cancel_registry — cooperative cancellation flags."""
from __future__ import annotations

from app.services import cancel_registry as cr


def setup_function(_):
    # Clear any state leaked from prior tests.
    cr._flags.clear()
    cr._metadata.clear()


def test_unknown_op_id_is_not_canceled():
    assert cr.is_canceled("nope") is False


def test_empty_op_id_is_not_canceled():
    assert cr.is_canceled("") is False
    assert cr.is_canceled(None) is False  # type: ignore[arg-type]


def test_start_finish_lifecycle():
    cr.start("step3_20260526", {"step": 3, "date": "20260526"})
    assert cr.is_canceled("step3_20260526") is False
    cr.finish("step3_20260526")
    assert cr.is_canceled("step3_20260526") is False


def test_request_cancel_sets_flag():
    cr.start("op1")
    assert cr.request_cancel("op1") is True
    assert cr.is_canceled("op1") is True


def test_request_cancel_unknown_returns_false():
    assert cr.request_cancel("never-started") is False


def test_start_clears_prior_cancel_flag():
    cr.start("op1")
    cr.request_cancel("op1")
    assert cr.is_canceled("op1") is True
    # Re-using the same op_id (e.g. user re-clicks the button) clears the flag.
    cr.start("op1")
    assert cr.is_canceled("op1") is False


def test_list_running_excludes_canceled():
    cr.start("a")
    cr.start("b")
    cr.request_cancel("a")
    running = cr.list_running()
    assert "b" in running
    assert "a" not in running
