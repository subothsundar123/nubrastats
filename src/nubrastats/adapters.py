from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable
from typing import Any

import pandas as pd

from . import utils


def _pick(data: dict[str, Any], keys: tuple[str, ...], default: Any = None) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return default


def orders_to_trades(
    orders: Iterable[dict[str, Any]],
    *,
    price_scale: str = "paise",
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for order in orders:
        qty = _pick(order, ("filled_qty", "order_qty", "trade_qty", "quantity"), 0)
        if qty in (None, 0, "0"):
            continue

        raw_price = _pick(
            order,
            ("avg_filled_price", "trade_price", "order_price", "price", "last_traded_price"),
            0,
        )
        price = float(raw_price or 0)
        if price_scale.lower() == "paise":
            price = price / 100.0

        symbol = _pick(order, ("symbol", "display_name", "stock_name", "asset"), "UNKNOWN")
        side = utils.normalize_side(_pick(order, ("order_side", "side"), ""))
        timestamp = utils.to_timestamp(
            _pick(order, ("filled_time", "order_time", "last_modified", "timestamp"), None)
        )
        fee = float(_pick(order, ("brokerage", "fee", "charges"), 0.0) or 0.0)
        if price_scale.lower() == "paise":
            fee = fee / 100.0

        rows.append(
            {
                "timestamp": timestamp,
                "symbol": str(symbol),
                "side": side,
                "quantity": float(qty),
                "price": float(price),
                "fee": fee,
                "order_id": _pick(order, ("order_id", "exchange_order_id"), None),
                "tag": _pick(order, ("tag",), None),
                "strategy_id": _pick(order, ("strategy_id",), None),
                "status": _pick(order, ("order_status", "status"), None),
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "timestamp",
                "symbol",
                "side",
                "quantity",
                "price",
                "fee",
                "order_id",
                "tag",
                "strategy_id",
                "status",
            ]
        )
    df = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
    return df


def realized_pnl_fifo(trades: pd.DataFrame) -> pd.DataFrame:
    """
    Add realized PnL using per-symbol FIFO matching.
    Supports both long and short inventory.
    """
    if trades.empty:
        out = trades.copy()
        out["realized_pnl"] = []
        out["cum_realized_pnl"] = []
        return out

    required = {"timestamp", "symbol", "side", "quantity", "price"}
    missing = required - set(trades.columns)
    if missing:
        raise ValueError(f"Missing required columns for FIFO PnL: {sorted(missing)}")

    df = trades.copy().sort_values("timestamp").reset_index(drop=True)
    df["fee"] = pd.to_numeric(df.get("fee", 0.0), errors="coerce").fillna(0.0)
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0.0)
    df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0.0)

    books: dict[str, deque[tuple[float, float]]] = defaultdict(deque)
    realized: list[float] = []

    for _, row in df.iterrows():
        symbol = str(row["symbol"])
        side = utils.normalize_side(str(row["side"]))
        qty = float(row["quantity"])
        price = float(row["price"])
        fee = float(row["fee"])

        qty_signed = qty if side == "BUY" else -qty
        remaining = qty_signed
        pnl = 0.0
        book = books[symbol]

        while remaining != 0 and book and (book[0][0] * remaining < 0):
            lot_qty, lot_price = book[0]
            matched_qty = min(abs(lot_qty), abs(remaining))
            sign = 1.0 if lot_qty > 0 else -1.0
            pnl += matched_qty * (price - lot_price) * sign

            if abs(lot_qty) == matched_qty:
                book.popleft()
            else:
                leftover = abs(lot_qty) - matched_qty
                book[0] = ((leftover if lot_qty > 0 else -leftover), lot_price)

            remaining = remaining + matched_qty if remaining < 0 else remaining - matched_qty

        if remaining != 0:
            book.append((remaining, price))

        pnl -= fee
        realized.append(pnl)

    df["realized_pnl"] = realized
    df["cum_realized_pnl"] = df["realized_pnl"].cumsum()
    return df


def equity_curve_from_trades(
    trades: pd.DataFrame,
    *,
    starting_capital: float = 100000.0,
) -> pd.Series:
    if trades.empty:
        return pd.Series([starting_capital], index=[pd.Timestamp.utcnow()], name="equity")

    df = trades.copy()
    if "realized_pnl" not in df.columns:
        df = realized_pnl_fifo(df)
    df = df.sort_values("timestamp").reset_index(drop=True)
    equity = starting_capital + df["realized_pnl"].cumsum()
    s = pd.Series(equity.values, index=pd.to_datetime(df["timestamp"]), name="equity")
    return s


def returns_from_trades(
    trades: pd.DataFrame,
    *,
    starting_capital: float = 100000.0,
) -> pd.Series:
    equity = equity_curve_from_trades(trades, starting_capital=starting_capital)
    return utils.to_series(utils.to_returns(equity))

