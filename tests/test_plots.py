import pandas as pd

from nubrastats import plots


def test_plot_functions_smoke():
    returns = pd.Series(
        [0.01, -0.005, 0.002, 0.004, -0.001, 0.003],
        index=pd.date_range("2026-01-01", periods=6, freq="D"),
    )
    equity = (1 + returns).cumprod() * 100000
    fig1 = plots.equity_curve(equity, show=False)
    fig2 = plots.drawdown(equity=equity, show=False)
    fig3 = plots.monthly_heatmap(returns, show=False)
    fig4 = plots.rolling_sharpe(returns, show=False)
    assert fig1 is not None
    assert fig2 is not None
    assert fig3 is not None
    assert fig4 is not None


def test_advanced_plot_functions_smoke():
    returns = pd.Series(
        [0.01, -0.005, 0.002, 0.004, -0.001, 0.003, 0.007, -0.002, 0.001, 0.005],
        index=pd.date_range("2026-01-01", periods=10, freq="D"),
    )
    benchmark = returns * 0.5

    fig1 = plots.cumulative_returns(returns, benchmark=benchmark, show=False)
    fig2 = plots.yearly_returns(returns, benchmark=benchmark, show=False)
    fig3 = plots.returns_distribution(returns, benchmark=benchmark, show=False)
    fig4 = plots.rolling_volatility(returns, benchmark=benchmark, show=False)
    fig5 = plots.rolling_sortino(returns, show=False)
    fig6 = plots.rolling_beta(returns, benchmark, show=False)
    fig7 = plots.drawdown_periods(returns, show=False)
    fig8 = plots.underwater(returns, show=False)
    fig9 = plots.return_quantiles(returns, show=False)

    assert fig1 is not None
    assert fig2 is not None
    assert fig3 is not None
    assert fig4 is not None
    assert fig5 is not None
    assert fig6 is not None
    assert fig7 is not None
    assert fig8 is not None
    assert fig9 is not None
