import numpy as np

from nubrastats import adapters


def test_orders_to_trades_converts_price_from_paise():
    orders = [
        {
            "symbol": "RELIANCE",
            "order_side": "ORDER_SIDE_BUY",
            "filled_qty": 10,
            "avg_filled_price": 248000,
            "filled_time": 1730000000000000000,
        }
    ]
    trades = adapters.orders_to_trades(orders, price_scale="paise")
    assert len(trades) == 1
    assert np.isclose(trades.iloc[0]["price"], 2480.0)
    assert trades.iloc[0]["side"] == "BUY"


def test_realized_pnl_fifo_for_simple_round_trip():
    trades = adapters.orders_to_trades(
        [
            {
                "symbol": "RELIANCE",
                "order_side": "BUY",
                "filled_qty": 10,
                "avg_filled_price": 248000,
                "filled_time": 1730000000000000000,
            },
            {
                "symbol": "RELIANCE",
                "order_side": "SELL",
                "filled_qty": 10,
                "avg_filled_price": 249500,
                "filled_time": 1730003600000000000,
            },
        ],
        price_scale="paise",
    )
    out = adapters.realized_pnl_fifo(trades)
    # Second trade closes first one; expected pnl = (2495 - 2480)*10 = 150
    assert np.isclose(out.iloc[1]["realized_pnl"], 150.0)

