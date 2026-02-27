import numpy as np
import pandas as pd

from nubrastats import stats


def test_summary_returns_core_metrics():
    returns = pd.Series(
        [0.01, -0.005, 0.007, -0.003, 0.012],
        index=pd.date_range("2026-01-01", periods=5, freq="D"),
    )
    out = stats.summary(returns=returns)
    assert "Sharpe" in out.index
    assert "Max Drawdown" in out.index
    assert np.isfinite(out["Total Return"])


def test_max_drawdown_non_positive():
    returns = pd.Series(
        [0.02, -0.01, -0.03, 0.01],
        index=pd.date_range("2026-01-01", periods=4, freq="D"),
    )
    dd = stats.max_drawdown(returns=returns)
    assert dd <= 0


def test_trade_metrics_from_realized_pnl():
    trades = pd.DataFrame({"realized_pnl": [100, -50, 30, -20]})
    assert np.isfinite(stats.profit_factor(trades))
    assert np.isfinite(stats.expectancy(trades))
    assert 0 <= stats.win_rate_trades(trades) <= 1


def test_extended_stats_helpers_smoke():
    returns = pd.Series(
        [0.01, -0.005, 0.007, -0.003, 0.012, -0.004, 0.001],
        index=pd.date_range("2026-01-01", periods=7, freq="D"),
    )
    benchmark = returns * 0.6

    assert np.isfinite(stats.calmar(returns))
    assert np.isfinite(stats.value_at_risk(returns))
    assert np.isfinite(stats.conditional_value_at_risk(returns))
    assert np.isfinite(stats.beta(returns, benchmark))
    assert np.isfinite(stats.correlation(returns, benchmark))
    assert not stats.yearly_returns(returns).empty
    dd = stats.top_drawdowns(returns=returns, top=3)
    assert {"Started", "Valley", "Recovered", "Drawdown", "Days"} <= set(dd.columns)
