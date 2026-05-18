from __future__ import annotations

import pandas as pd

DATE_ONLY_FORMAT = "%Y-%m-%d"


def parse_date_only_series(series: pd.Series) -> pd.Series:
    """
    Parse date-only values while accepting both YYYY-MM-DD and YYYY/MM/DD.

    The return value is normalized to midnight timestamps so callers can safely
    compare and sort on calendar dates without time components.
    """
    if pd.api.types.is_datetime64_any_dtype(series):
        return pd.to_datetime(series, errors="coerce").dt.normalize()

    cleaned = series.astype("string").str.strip()
    cleaned = cleaned.str.replace("/", "-", regex=False)
    cleaned = cleaned.mask(cleaned == "")
    return pd.to_datetime(cleaned, errors="coerce", format=DATE_ONLY_FORMAT).dt.normalize()


def format_date_only_series(series: pd.Series, *, missing_value: str = "") -> pd.Series:
    """
    Format date-only values to the canonical YYYY-MM-DD string representation.
    """
    parsed = parse_date_only_series(series)
    formatted = parsed.dt.strftime(DATE_ONLY_FORMAT)
    if missing_value is not None:
        formatted = formatted.fillna(missing_value)
    return formatted
