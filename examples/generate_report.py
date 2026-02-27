import pandas as pd

import nubrastats as ns


def main() -> None:
    trades = ns.adapters.orders_to_trades(
        [
            {
                "symbol": "RELIANCE",
                "order_side": "BUY",
                "filled_qty": 10,
                "avg_filled_price": 248000,
                "filled_time": 1730000000000000000,
                "tag": "demo",
            },
            {
                "symbol": "RELIANCE",
                "order_side": "SELL",
                "filled_qty": 10,
                "avg_filled_price": 249500,
                "filled_time": 1730003600000000000,
                "tag": "demo",
            },
            {
                "symbol": "HDFCBANK",
                "order_side": "BUY",
                "filled_qty": 5,
                "avg_filled_price": 160000,
                "filled_time": 1730010000000000000,
                "tag": "demo",
            },
            {
                "symbol": "HDFCBANK",
                "order_side": "SELL",
                "filled_qty": 5,
                "avg_filled_price": 159500,
                "filled_time": 1730013600000000000,
                "tag": "demo",
            },
        ],
        price_scale="paise",
    )

    trades = ns.adapters.realized_pnl_fifo(trades)
    equity = ns.adapters.equity_curve_from_trades(trades, starting_capital=100000)
    returns = ns.utils.to_series(ns.utils.to_returns(equity))
    returns = pd.Series(
        returns.values,
        index=pd.date_range("2026-01-01", periods=len(returns), freq="D"),
    )

    ns.reports.metrics(returns=returns, trades=trades, display=True)
    out = ns.reports.html(
        returns=returns,
        trades=trades,
        title="NubraStats Demo Tearsheet",
        output="nubrastats-demo-report.html",
    )
    print(f"Report generated: {out}")


if __name__ == "__main__":
    main()
