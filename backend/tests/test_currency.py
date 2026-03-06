"""Tests for currency conversion and salary normalization."""

from unittest.mock import patch

from app.services.currency import (
    convert_to_pln,
    detect_salary_period,
    normalize_to_monthly,
    normalize_salary,
)


def test_convert_to_pln_none_inputs():
    """convert_to_pln returns None for None amount or currency."""
    assert convert_to_pln(None, "USD") is None
    assert convert_to_pln(100.0, None) is None
    assert convert_to_pln(100.0, "") is None


def test_convert_to_pln_pln_returns_amount():
    """convert_to_pln returns amount unchanged for PLN."""
    assert convert_to_pln(5000.0, "PLN") == 5000.0


def test_convert_to_pln_with_rates():
    """convert_to_pln converts using fetched rates."""
    with patch("app.services.currency._fetch_rates", return_value={"USD": 4.0, "PLN": 1.0}):
        assert convert_to_pln(100.0, "USD") == 400.0


def test_convert_to_pln_unknown_currency_returns_none():
    """convert_to_pln returns None for unknown currency."""
    with patch("app.services.currency._fetch_rates", return_value={"PLN": 1.0}):
        assert convert_to_pln(100.0, "XYZ") is None


def test_normalize_to_monthly_none_inputs():
    """normalize_to_monthly returns amount for None period."""
    assert normalize_to_monthly(100.0, None) == 100.0
    assert normalize_to_monthly(None, "hourly") is None


def test_normalize_to_monthly_hourly():
    """normalize_to_monthly converts hourly to monthly (x160)."""
    assert normalize_to_monthly(50.0, "hourly") == 8000.0


def test_normalize_to_monthly_daily():
    """normalize_to_monthly converts daily to monthly (x20)."""
    assert normalize_to_monthly(500.0, "daily") == 10000.0


def test_normalize_to_monthly_monthly_unchanged():
    """normalize_to_monthly returns amount for monthly."""
    assert normalize_to_monthly(10000.0, "monthly") == 10000.0


def test_detect_salary_period_explicit():
    """detect_salary_period returns explicit period when provided."""
    assert detect_salary_period(None, explicit_period="hourly") == "hourly"
    assert detect_salary_period(None, explicit_period="daily") == "daily"
    assert detect_salary_period(None, explicit_period="monthly") == "monthly"
    assert detect_salary_period(None, explicit_period="yearly") == "yearly"


def test_detect_salary_period_from_salary_type():
    """detect_salary_period infers from salary_type string."""
    assert detect_salary_period("100 PLN/h", url="") == "hourly"
    assert detect_salary_period("500/day", url="") == "daily"


def test_detect_salary_period_heuristic_pln():
    """detect_salary_period uses heuristic for low PLN values."""
    assert detect_salary_period(None, salary_max=200, currency="PLN") == "hourly"
    assert detect_salary_period(None, salary_max=5000, currency="PLN") == "monthly"


def test_detect_salary_period_default_monthly():
    """detect_salary_period defaults to monthly."""
    assert detect_salary_period(None, url="", source="") == "monthly"


def test_normalize_salary_populates_row():
    """normalize_salary populates salary_period and _pln fields."""
    from types import SimpleNamespace

    row = SimpleNamespace(
        salary_min=100.0,
        salary_max=150.0,
        salary_currency="PLN",
        salary_type=None,
        url="",
        source="",
    )
    with patch("app.services.currency._fetch_rates", return_value={"PLN": 1.0}):
        normalize_salary(row, explicit_period="hourly")
    assert row.salary_period == "hourly"
    assert row.salary_min_pln == 16000.0  # 100 * 160
    assert row.salary_max_pln == 24000.0  # 150 * 160


def test_normalize_salary_none_salary():
    """normalize_salary clears fields when salary is None."""
    from types import SimpleNamespace

    row = SimpleNamespace(
        salary_min=None,
        salary_max=None,
        salary_currency=None,
        salary_type=None,
        url="",
        source="",
    )
    normalize_salary(row)
    assert row.salary_period is None
    assert row.salary_min_pln is None
    assert row.salary_max_pln is None
