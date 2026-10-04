from datetime import date
from decimal import Decimal

from pipeline import _safe_float, _safe_int, _parse_date, _serialize_row


def test_safe_float_basic():
    assert _safe_float(85) == 85.0
    assert _safe_float("85.5") == 85.5
    assert _safe_float("85%") == 85.0
    assert _safe_float("1,200") == 1200.0
    assert _safe_float(None) == 0.0
    assert _safe_float("abc") == 0.0
    assert _safe_float("-10.5") == -10.5


def test_safe_int_basic():
    assert _safe_int(85) == 85
    assert _safe_int("85.7") == 85
    assert _safe_int(None) is None
    assert _safe_int("abc") is None


def test_parse_date_formats():
    assert _parse_date("2026-03-15") == date(2026, 3, 15)
    assert _parse_date("15/03/2026") == date(2026, 3, 15)
    assert _parse_date("2026/03/15") == date(2026, 3, 15)
    assert _parse_date("15-03-2026") == date(2026, 3, 15)
    assert _parse_date("Unknown") is None
    assert _parse_date(None) is None
    assert _parse_date("invalid") is None


def test_serialize_row():
    row = {
        "id": 1,
        "audit_date": date(2026, 3, 15),
        "revenue_vnd": Decimal("250000000000.00"),
        "company_name": "ABC",
    }
    out = _serialize_row(row)
    assert out["audit_date"] == "2026-03-15"
    assert out["revenue_vnd"] == 250000000000.0
    assert out["id"] == 1
    assert out["company_name"] == "ABC"
