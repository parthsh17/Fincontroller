from datetime import date
from decimal import Decimal
from rapidfuzz import fuzz


def fuzzy_score(a: str | None, b: str | None) -> float:
    if a is None or b is None:
        return 0.0
    s_a = str(a).strip()
    s_b = str(b).strip()
    if not s_a or not s_b:
        return 0.0
    return float(fuzz.token_sort_ratio(s_a, s_b)) / 100.0


def amount_within_tolerance(
    a: Decimal, b: Decimal, pct: float, abs_tol: float
) -> bool:
    diff = abs(a - b)
    max_tol = max(a * Decimal(str(pct)) / Decimal("100"), Decimal(str(abs_tol)))
    return diff <= max_tol


def date_within_window(a: date, b: date, window_days: int) -> bool:
    return abs((a - b).days) <= window_days
