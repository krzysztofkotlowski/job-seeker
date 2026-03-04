"""Currency conversion + salary normalization using Frankfurter API (ECB rates)."""

import logging
import time
from typing import Optional

import requests

log = logging.getLogger(__name__)

_cache: dict = {}
_cache_ts: float = 0
_CACHE_TTL = 86400  # 24 hours

FRANKFURTER_URL = "https://api.frankfurter.dev/v1/latest"


def _fetch_rates() -> dict[str, float]:
    """Fetch exchange rates with PLN as base. Returns {currency: rate_to_pln}."""
    global _cache, _cache_ts
    now = time.time()
    if _cache and (now - _cache_ts) < _CACHE_TTL:
        return _cache

    try:
        resp = requests.get(
            FRANKFURTER_URL,
            params={"base": "PLN", "symbols": "USD,EUR,GBP,CHF"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        rates_from_pln = data.get("rates", {})
        rates_to_pln = {}
        for cur, rate in rates_from_pln.items():
            if rate and rate > 0:
                rates_to_pln[cur] = 1.0 / rate
        rates_to_pln["PLN"] = 1.0
        _cache = rates_to_pln
        _cache_ts = now
        log.info("Currency rates updated: %s", rates_to_pln)
    except Exception as e:
        log.warning("Failed to fetch currency rates: %s", e)
        if not _cache:
            _cache = {"PLN": 1.0, "USD": 4.0, "EUR": 4.3, "GBP": 5.1, "CHF": 4.5}
            _cache_ts = now

    return _cache


def convert_to_pln(amount: Optional[float], currency: Optional[str]) -> Optional[float]:
    if amount is None or not currency:
        return None
    cur = currency.upper().strip()
    if cur == "PLN":
        return amount
    rates = _fetch_rates()
    rate = rates.get(cur)
    if rate is None:
        return None
    return round(amount * rate, 2)


def normalize_to_monthly(amount: Optional[float], period: Optional[str]) -> Optional[float]:
    if amount is None or not period:
        return amount
    p = period.lower()
    if p == "hourly":
        return round(amount * 160, 2)
    if p == "daily":
        return round(amount * 20, 2)
    return amount


def detect_salary_period(
    salary_type: Optional[str],
    url: str = "",
    source: str = "",
    explicit_period: Optional[str] = None,
    salary_max: Optional[float] = None,
    currency: Optional[str] = None,
) -> str:
    """Infer pay period from salary type string, URL context, and heuristics."""
    if explicit_period:
        ep = explicit_period.lower()
        if ep in ("hourly", "hour", "h"):
            return "hourly"
        if ep in ("daily", "day", "d"):
            return "daily"
        if ep in ("monthly", "month", "m"):
            return "monthly"
        if ep in ("yearly", "year", "annual"):
            return "yearly"

    if salary_type:
        st = salary_type.lower()
        if any(k in st for k in ["/h", "per hour", "hourly", "/godz", "godzin"]):
            return "hourly"
        if any(k in st for k in ["/day", "per day", "daily", "/dzie", "dzień"]):
            return "daily"
        url_lower = url.lower()
        if "/h" in st or "usd/h" in url_lower:
            return "hourly"

    # Heuristic: PLN values under 500 are almost certainly hourly rates
    if salary_max is not None and (currency or "").upper() == "PLN" and 0 < salary_max < 500:
        log.info("Heuristic: %s PLN looks hourly (max=%s)", currency, salary_max)
        return "hourly"
    # USD/EUR under 120 are likely hourly
    if salary_max is not None and (currency or "").upper() in ("USD", "EUR") and 0 < salary_max < 120:
        log.info("Heuristic: %s looks hourly (max=%s)", currency, salary_max)
        return "hourly"

    return "monthly"


def normalize_salary(row, explicit_period: Optional[str] = None) -> None:
    """Populate salary_period, salary_min_pln, salary_max_pln on a JobRow."""
    if row.salary_min is None and row.salary_max is None:
        row.salary_period = None
        row.salary_min_pln = None
        row.salary_max_pln = None
        return

    period = detect_salary_period(
        row.salary_type,
        row.url or "",
        row.source or "",
        explicit_period=explicit_period,
        salary_max=row.salary_max,
        currency=row.salary_currency,
    )
    row.salary_period = period

    min_pln = convert_to_pln(row.salary_min, row.salary_currency)
    max_pln = convert_to_pln(row.salary_max, row.salary_currency)

    row.salary_min_pln = normalize_to_monthly(min_pln, period)
    row.salary_max_pln = normalize_to_monthly(max_pln, period)
