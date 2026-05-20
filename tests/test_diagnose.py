"""Unit tests for app.services.diagnose — connection-error → user hint mapping.

Coverage: every pattern branch (DNS, timeout, 403, 404, invalid_grant, missing
SA file, SSL, quota), plus the no-match fallback. The bug field-tested on
2026-05-20 was DNS resolution failure ('getaddrinfo failed') with no UI hint
shipped — these tests pin the public contract so the hint stays put.
"""
from __future__ import annotations

import pytest

from app.services.diagnose import diagnose


def test_returns_none_for_empty_input():
    assert diagnose("", scope="sheet") is None
    assert diagnose(None, scope="sheet") is None  # type: ignore[arg-type]


def test_returns_none_for_unknown_error():
    out = diagnose("some totally unexpected error xyzzy", scope="sheet")
    assert out is None


def test_dns_getaddrinfo_failed_field_report():
    """The exact field-reported message from Issue #1 (2026-05-20)."""
    err = (
        "HTTPSConnectionPool(host='sheets.googleapis.com', port=443): "
        "Max retries exceeded with url: /v4/spreadsheets/X "
        "(Caused by NewConnectionError(...Failed to resolve "
        "'sheets.googleapis.com' ([Errno 11001] getaddrinfo failed)\"))"
    )
    out = diagnose(err, scope="sheet")
    assert out is not None
    assert "DNS" in out["title"]
    assert out["is_code_bug"] is False
    assert len(out["suggestions"]) >= 3
    assert any("熱點" in s or "防火牆" in s or "VPN" in s for s in out["suggestions"])


def test_dns_alternative_phrasings():
    cases = [
        "Name or service not known",
        "Temporary failure in name resolution",
        "Failed to resolve 'oauth2.googleapis.com'",
        "nodename nor servname provided",
    ]
    for err in cases:
        out = diagnose(err, scope="sheet")
        assert out is not None, f"DNS not matched for: {err!r}"
        assert "DNS" in out["title"]


def test_timeout():
    for err in ("Read timed out", "Connection timed out",
                "ConnectTimeoutError", "Connection refused"):
        out = diagnose(err, scope="sheet")
        assert out is not None, err
        assert "逾時" in out["title"]


def test_403_forbidden_admission_scope():
    out = diagnose("403 Forbidden: The caller does not have permission",
                   scope="sheet")
    assert out is not None
    assert "Sheet" in out["title"]
    assert any("共用" in s or "編輯者" in s for s in out["suggestions"])


def test_403_forbidden_schedule_scope_mentions_schedule_sheet():
    out = diagnose("permission_denied", scope="schedule_sheet")
    assert out is not None
    assert "排班 Sheet" in out["title"]


def test_404_not_found():
    out = diagnose("404 Requested entity was not found.", scope="sheet")
    assert out is not None
    assert "找不到 Sheet" in out["title"]
    assert any("Sheet ID" in s for s in out["suggestions"])


def test_invalid_grant():
    for err in ("invalid_grant: Invalid JWT signature",
                "Could not deserialize key data"):
        out = diagnose(err, scope="sheet")
        assert out is not None, err
        assert "金鑰無效" in out["title"]


def test_sa_file_missing_chinese_message():
    """sheet_service.connection_check produces 找不到 service-account…
    when the file is absent."""
    out = diagnose("找不到 service-account 檔：[Errno 2] No such file",
                   scope="sheet")
    assert out is not None
    assert "service_account.json" in out["title"]


def test_ssl_handshake():
    out = diagnose("SSLError: CERTIFICATE_VERIFY_FAILED", scope="sheet")
    assert out is not None
    assert "SSL" in out["title"]


def test_quota():
    out = diagnose("429 RATE_LIMIT_EXCEEDED quota exceeded", scope="sheet")
    assert out is not None
    assert "配額" in out["title"]


def test_shape_contract():
    """All hints must carry the same key set so the UI renderer doesn't
    have to guard each field."""
    out = diagnose("getaddrinfo failed", scope="sheet")
    assert out is not None
    assert set(out.keys()) >= {"title", "cause", "suggestions", "is_code_bug"}
    assert isinstance(out["suggestions"], list)
    assert all(isinstance(s, str) and s for s in out["suggestions"])
