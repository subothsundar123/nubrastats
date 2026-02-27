from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

import numpy as np
import pandas as pd


def to_series(data: pd.Series | pd.DataFrame | Iterable[float]) -> pd.Series:
    if isinstance(data, pd.Series):
        return data.copy()
    if isinstance(data, pd.DataFrame):
        if data.shape[1] == 0:
            return pd.Series(dtype=float)
        return data.iloc[:, 0].copy()
    return pd.Series(list(data), dtype=float)


def ensure_datetime_index(
    data: pd.Series | pd.DataFrame,
    *,
    fallback_start: datetime | None = None,
    freq: str = "D",
) -> pd.Series | pd.DataFrame:
    obj = data.copy()
    if isinstance(obj.index, pd.DatetimeIndex):
        return obj.sort_index()

    try:
        obj.index = pd.to_datetime(obj.index)
        return obj.sort_index()
    except Exception:
        start = fallback_start or datetime.utcnow()
        obj.index = pd.date_range(start=start, periods=len(obj), freq=freq)
        return obj.sort_index()


def to_returns(equity: pd.Series | pd.DataFrame) -> pd.Series | pd.DataFrame:
    eq = ensure_datetime_index(equity)
    returns = eq.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return returns


def to_equity(
    returns: pd.Series | pd.DataFrame,
    *,
    start_balance: float = 100000.0,
) -> pd.Series | pd.DataFrame:
    ret = ensure_datetime_index(returns)
    ret = ret.fillna(0.0)
    return start_balance * (1.0 + ret).cumprod()


def annualization_factor(periods_per_year: int = 252) -> int:
    return max(int(periods_per_year), 1)


def safe_div(numerator: float, denominator: float) -> float:
    if denominator == 0 or np.isnan(denominator):
        return np.nan
    return numerator / denominator


def monthly_returns_matrix(returns: pd.Series) -> pd.DataFrame:
    s = to_series(returns).dropna()
    s = ensure_datetime_index(s)
    try:
        monthly = s.resample("ME").apply(lambda x: (1 + x).prod() - 1)
    except Exception:
        monthly = s.resample("M").apply(lambda x: (1 + x).prod() - 1)
    out = monthly.to_frame("return")
    out["year"] = out.index.year
    out["month"] = out.index.strftime("%b")
    pivot = out.pivot(index="year", columns="month", values="return").fillna(0.0)
    ordered = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    for month in ordered:
        if month not in pivot.columns:
            pivot[month] = 0.0
    return pivot[ordered].sort_index()


def normalize_side(value: str) -> str:
    s = str(value).strip().upper()
    if s in {"BUY", "ORDER_SIDE_BUY", "B"}:
        return "BUY"
    if s in {"SELL", "ORDER_SIDE_SELL", "S"}:
        return "SELL"
    return s


def to_timestamp(value: object) -> pd.Timestamp:
    if value is None:
        return pd.Timestamp.utcnow()
    try:
        if isinstance(value, (int, float)):
            # Try ns first, then ms, then s.
            if value > 1e15:
                return pd.to_datetime(int(value), unit="ns", utc=True).tz_convert(None)
            if value > 1e12:
                return pd.to_datetime(int(value), unit="ms", utc=True).tz_convert(None)
            return pd.to_datetime(int(value), unit="s", utc=True).tz_convert(None)
        return pd.to_datetime(value, utc=True).tz_convert(None)
    except Exception:
        return pd.Timestamp.utcnow()
