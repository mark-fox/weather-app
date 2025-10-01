from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

@dataclass
class DateRange:
    start: date
    end: date

def _parse_iso(d: Optional[str]) -> Optional[date]:
    if not d:
        return None
    try:
        return datetime.strptime(d, "%Y-%m-%d").date()
    except ValueError:
        return None

def validate_date_range(start_s: Optional[str], end_s: Optional[str], max_days: int = 31) -> Optional[DateRange]:
    """
    Returns DateRange if both provided and valid; returns None if both empty.
    Raises ValueError with a friendly message on invalid input.
    """
    if not start_s and not end_s:
        return None

    start = _parse_iso(start_s)
    end = _parse_iso(end_s)
    if not start or not end:
        raise ValueError("Dates must be in YYYY-MM-DD format.")

    if start > end:
        raise ValueError("Start date must be on or before end date.")

    span = (end - start).days + 1
    if span > max_days:
        raise ValueError(f"Date range too large ({span} days). Max {max_days} days.")

    return DateRange(start=start, end=end)
