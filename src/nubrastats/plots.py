# ruff: noqa: E402

from __future__ import annotations

import os
import sys
from io import BytesIO
from typing import Any

import matplotlib
import numpy as np


def _configure_matplotlib_backend() -> None:
    forced = os.environ.get("NUBRASTATS_MPL_BACKEND")
    if forced:
        matplotlib.use(forced, force=True)
        return

    # Use non-interactive backend in headless/CI/test environments.
    if os.environ.get("NUBRASTATS_HEADLESS") == "1" or os.environ.get("CI") == "true":
        matplotlib.use("Agg", force=True)
        return
    if "pytest" in sys.modules:
        matplotlib.use("Agg", force=True)


_configure_matplotlib_backend()

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from . import stats, utils

sns.set_theme(style="whitegrid")


def _save_or_show(
    fig: plt.Figure,
    *,
    show: bool = True,
    savefig: dict[str, Any] | None = None,
) -> plt.Figure:
    if savefig:
        fig.savefig(**savefig)
    if show:
        plt.show()
    return fig


def figure_to_png_bytes(fig: plt.Figure) -> bytes:
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=120)
    return buf.getvalue()


def _render_note(fig: plt.Figure, note: str | None, default_bottom: float = 0.03) -> None:
    if note:
        fig.text(0.01, 0.01, note, fontsize=8, color="#6b7280", va="bottom")
        fig.tight_layout(rect=[0, 0.07, 1, 1])
        return
    fig.tight_layout(rect=[0, default_bottom, 1, 1])


def equity_curve(
    equity: pd.Series,
    benchmark: pd.Series | None = None,
    *,
    title: str = "Equity Curve",
    strategy_label: str | None = None,
    benchmark_label: str | None = None,
    subtitle_note: str | None = None,
    show: bool = True,
    savefig: dict[str, Any] | None = None,
) -> plt.Figure:
    eq = utils.to_series(equity).dropna()
    eq = utils.ensure_datetime_index(eq)
    strategy_name = (strategy_label or getattr(eq, "name", "") or "Strategy").strip()
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(eq.index, eq.values, label=strategy_name, linewidth=2)
    if benchmark is not None:
        bench = utils.to_series(benchmark).dropna()
        bench = utils.ensure_datetime_index(bench)
        bench_name = (benchmark_label or getattr(bench, "name", "") or "Benchmark").strip()
        ax.plot(bench.index, bench.values, label=bench_name, linewidth=1.5, alpha=0.8)
    ax.set_title(title)
    ax.set_ylabel("Equity (Notional Capital)")
    ax.legend(loc="best")
    footer_lines = [
        "Equity curve = compounded capital from periodic returns (base capital: 100000)."
    ]
    if subtitle_note:
        footer_lines.append(subtitle_note)
    fig.text(
        0.01,
        0.01,
        "\n".join(footer_lines),
        fontsize=8,
        color="#6b7280",
        va="bottom",
    )
    fig.tight_layout(rect=[0, 0.08, 1, 1])
    return _save_or_show(fig, show=show, savefig=savefig)


def drawdown(
    returns: pd.Series | None = None,
    equity: pd.Series | None = None,
    *,
    title: str = "Drawdown",
    subtitle_note: str | None = None,
    show: bool = True,
    savefig: dict[str, Any] | None = None,
) -> plt.Figure:
    dd = stats.drawdown_series(returns=returns, equity=equity)
    dd = utils.ensure_datetime_index(dd)
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.fill_between(dd.index, dd.values, 0.0, color="#d62728", alpha=0.35)
    ax.set_title(title)
    ax.set_ylabel("Drawdown")
    _render_note(fig, subtitle_note, default_bottom=0.03)
    return _save_or_show(fig, show=show, savefig=savefig)


def monthly_heatmap(
    returns: pd.Series,
    *,
    title: str = "Monthly Returns Heatmap",
    subtitle_note: str | None = None,
    show: bool = True,
    savefig: dict[str, Any] | None = None,
) -> plt.Figure:
    matrix = utils.monthly_returns_matrix(utils.to_series(returns))
    fig, ax = plt.subplots(figsize=(10, 4))
    sns.heatmap(matrix * 100.0, cmap="RdYlGn", center=0.0, annot=True, fmt=".1f", ax=ax)
    ax.set_title(title)
    ax.set_xlabel("Month")
    ax.set_ylabel("Year")
    _render_note(fig, subtitle_note, default_bottom=0.03)
    return _save_or_show(fig, show=show, savefig=savefig)


def pnl_distribution(
    trades: pd.DataFrame,
    *,
    title: str = "Trade PnL Distribution",
    subtitle_note: str | None = None,
    show: bool = True,
    savefig: dict[str, Any] | None = None,
) -> plt.Figure:
    series = pd.Series(dtype=float)
    if "realized_pnl" in trades.columns:
        series = pd.to_numeric(trades["realized_pnl"], errors="coerce").dropna()
    elif "pnl" in trades.columns:
        series = pd.to_numeric(trades["pnl"], errors="coerce").dropna()

    fig, ax = plt.subplots(figsize=(8, 3))
    if not series.empty:
        sns.histplot(series, bins=30, kde=True, ax=ax, color="#1f77b4")
    ax.set_title(title)
    ax.set_xlabel("PnL")
    _render_note(fig, subtitle_note, default_bottom=0.03)
    return _save_or_show(fig, show=show, savefig=savefig)


def rolling_sharpe(
    returns: pd.Series,
    *,
    window: int = 63,
    rf: float = 0.0,
    periods_per_year: int = 252,
    title: str = "Rolling Sharpe",
    subtitle_note: str | None = None,
    show: bool = True,
    savefig: dict[str, Any] | None = None,
) -> plt.Figure:
    ret = utils.to_series(returns).dropna()
    rf_period = rf / periods_per_year

    # Avoid empty output when users pick short ranges (for example intraday + few days).
    effective_window = min(window, max(len(ret), 1))
    if effective_window < 2:
        sharpe = pd.Series(index=ret.index, dtype=float)
    else:
        min_periods = min(5, effective_window)
        rolling_mean = (ret - rf_period).rolling(
            window=effective_window,
            min_periods=min_periods,
        ).mean()
        rolling_std = ret.rolling(window=effective_window, min_periods=min_periods).std(ddof=1)
        sharpe = rolling_mean / rolling_std * (periods_per_year ** 0.5)
        sharpe = sharpe.replace([float("inf"), float("-inf")], pd.NA)

    fig, ax = plt.subplots(figsize=(10, 3))
    ax.plot(sharpe.index, sharpe.values, color="#9467bd")
    ax.axhline(0.0, color="black", linewidth=1)
    if effective_window != window:
        ax.set_title(f"{title} (window={effective_window})")
    else:
        ax.set_title(title)
    ax.set_ylabel("Sharpe")
    _render_note(fig, subtitle_note, default_bottom=0.03)
    return _save_or_show(fig, show=show, savefig=savefig)


def _align_returns(
    returns: pd.Series,
    benchmark: pd.Series | None = None,
) -> tuple[pd.Series, pd.Series | None]:
    strat = utils.to_series(returns).dropna()
    strat = utils.ensure_datetime_index(strat)
    if benchmark is None:
        return strat, None
    bench = utils.to_series(benchmark).dropna()
    bench = utils.ensure_datetime_index(bench)
    aligned = pd.concat([strat.rename("strategy"), bench.rename("benchmark")], axis=1, join="inner")
    aligned = aligned.dropna()
    if aligned.empty:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    return aligned.iloc[:, 0], aligned.iloc[:, 1]


def _rolling_window(window: int, series_len: int, *, min_ready: int = 5) -> tuple[int, int]:
    effective_window = min(max(int(window), 1), max(series_len, 1))
    min_periods = min(min_ready, effective_window)
    return effective_window, min_periods


def cumulative_returns(
    returns: pd.Series,
    benchmark: pd.Series | None = None,
    *,
    title: str = "Cumulative Returns vs Benchmark",
    strategy_label: str = "Strategy",
    benchmark_label: str = "Benchmark",
    log_scale: bool = False,
    match_volatility: bool = False,
    show: bool = True,
    savefig: dict[str, Any] | None = None,
) -> plt.Figure:
    strat, bench = _align_returns(returns, benchmark)
    fig, ax = plt.subplots(figsize=(10, 4))
    if strat.empty:
        ax.set_title(f"{title} (No data)")
        return _save_or_show(fig, show=show, savefig=savefig)

    strat_ret = strat.copy()
    bench_ret = bench.copy() if bench is not None else None
    if bench_ret is not None and match_volatility:
        strat_std = float(strat_ret.std(ddof=1))
        bench_std = float(bench_ret.std(ddof=1))
        if bench_std != 0 and not np.isnan(bench_std):
            bench_ret = bench_ret * (strat_std / bench_std)

    strat_curve = (1.0 + strat_ret.fillna(0.0)).cumprod() - 1.0
    if log_scale:
        ax.plot(strat_curve.index, np.log1p(strat_curve.values), label=strategy_label, linewidth=2)
        if bench_ret is not None:
            bench_curve = (1.0 + bench_ret.fillna(0.0)).cumprod() - 1.0
            ax.plot(
                bench_curve.index,
                np.log1p(bench_curve.values),
                label=benchmark_label,
                linewidth=1.6,
                alpha=0.85,
            )
        ax.set_ylabel("log(1 + cumulative return)")
    else:
        ax.plot(strat_curve.index, strat_curve.values * 100.0, label=strategy_label, linewidth=2)
        if bench_ret is not None:
            bench_curve = (1.0 + bench_ret.fillna(0.0)).cumprod() - 1.0
            ax.plot(
                bench_curve.index,
                bench_curve.values * 100.0,
                label=benchmark_label,
                linewidth=1.6,
                alpha=0.85,
            )
        ax.set_ylabel("Cumulative Return (%)")
    ax.axhline(0.0, color="#111827", linewidth=1, alpha=0.7)
    ax.set_title(title)
    ax.legend(loc="best")
    _render_note(fig, None, default_bottom=0.03)
    return _save_or_show(fig, show=show, savefig=savefig)


def yearly_returns(
    returns: pd.Series,
    benchmark: pd.Series | None = None,
    *,
    title: str = "EOY Returns vs Benchmark",
    strategy_label: str = "Strategy",
    benchmark_label: str = "Benchmark",
    show: bool = True,
    savefig: dict[str, Any] | None = None,
) -> plt.Figure:
    strat = stats.yearly_returns(returns)
    bench = stats.yearly_returns(benchmark) if benchmark is not None else None
    bench_years = set(bench.index.tolist()) if bench is not None else set()
    years = sorted(set(strat.index.tolist()) | bench_years)
    fig, ax = plt.subplots(figsize=(10, 4))
    if not years:
        ax.set_title(f"{title} (No data)")
        return _save_or_show(fig, show=show, savefig=savefig)

    idx = np.arange(len(years), dtype=float)
    width = 0.38
    strat_vals = [float(strat.get(y, np.nan)) * 100.0 for y in years]
    if benchmark is not None:
        bench_vals = (
            [float(bench.get(y, np.nan)) * 100.0 for y in years] if bench is not None else []
        )
        ax.bar(idx - width / 2, bench_vals, width=width, label=benchmark_label, alpha=0.75)
        ax.bar(idx + width / 2, strat_vals, width=width, label=strategy_label, alpha=0.9)
    else:
        ax.bar(idx, strat_vals, width=0.6, label=strategy_label, alpha=0.9)

    ax.axhline(0.0, color="#111827", linewidth=1, alpha=0.8)
    ax.set_xticks(idx)
    ax.set_xticklabels([str(y) for y in years], rotation=30)
    ax.set_title(title)
    ax.set_ylabel("Return (%)")
    ax.legend(loc="best")
    _render_note(fig, None, default_bottom=0.03)
    return _save_or_show(fig, show=show, savefig=savefig)


def returns_distribution(
    returns: pd.Series,
    benchmark: pd.Series | None = None,
    *,
    title: str = "Distribution of Monthly Returns",
    strategy_label: str = "Strategy",
    benchmark_label: str = "Benchmark",
    show: bool = True,
    savefig: dict[str, Any] | None = None,
) -> plt.Figure:
    strat = utils.to_series(returns).dropna()
    strat = utils.ensure_datetime_index(strat)
    strat_month = strat.resample("ME").apply(lambda x: (1.0 + x).prod() - 1.0)

    fig, ax = plt.subplots(figsize=(10, 4))
    if strat_month.empty:
        ax.set_title(f"{title} (No data)")
        return _save_or_show(fig, show=show, savefig=savefig)
    sns.histplot(
        strat_month * 100.0,
        bins=22,
        kde=True,
        stat="density",
        alpha=0.45,
        label=strategy_label,
        ax=ax,
    )

    if benchmark is not None:
        bench = utils.to_series(benchmark).dropna()
        bench = utils.ensure_datetime_index(bench)
        bench_month = bench.resample("ME").apply(lambda x: (1.0 + x).prod() - 1.0)
        if not bench_month.empty:
            sns.histplot(
                bench_month * 100.0,
                bins=22,
                kde=True,
                stat="density",
                alpha=0.35,
                label=benchmark_label,
                ax=ax,
            )

    ax.set_title(title)
    ax.set_xlabel("Monthly Return (%)")
    ax.legend(loc="best")
    _render_note(fig, None, default_bottom=0.03)
    return _save_or_show(fig, show=show, savefig=savefig)


def daily_active_returns(
    returns: pd.Series,
    *,
    title: str = "Daily Active Returns",
    show: bool = True,
    savefig: dict[str, Any] | None = None,
) -> plt.Figure:
    ret = utils.to_series(returns).dropna()
    ret = utils.ensure_datetime_index(ret)
    active = ((1.0 + ret).cumprod() - 1.0) * 100.0

    fig, ax = plt.subplots(figsize=(10, 3.5))
    if not active.empty:
        ax.fill_between(active.index, 0.0, active.values, color="#1f77b4", alpha=0.45)
        ax.plot(active.index, active.values, color="#1f77b4", linewidth=1.1)
    ax.axhline(0.0, color="#111827", linewidth=1, alpha=0.8)
    ax.set_title(title)
    ax.set_ylabel("Cumulative Return (%)")
    _render_note(fig, None, default_bottom=0.03)
    return _save_or_show(fig, show=show, savefig=savefig)


def rolling_volatility(
    returns: pd.Series,
    benchmark: pd.Series | None = None,
    *,
    window: int = 63,
    periods_per_year: int = 252,
    title: str = "Rolling Volatility",
    strategy_label: str = "Strategy",
    benchmark_label: str = "Benchmark",
    show: bool = True,
    savefig: dict[str, Any] | None = None,
) -> plt.Figure:
    strat, bench = _align_returns(returns, benchmark)
    fig, ax = plt.subplots(figsize=(10, 3.3))
    if strat.empty:
        ax.set_title(f"{title} (No data)")
        return _save_or_show(fig, show=show, savefig=savefig)

    win, min_periods = _rolling_window(window, len(strat))
    strat_vol = strat.rolling(window=win, min_periods=min_periods).std(ddof=1) * np.sqrt(
        max(periods_per_year, 1)
    )
    ax.plot(strat_vol.index, strat_vol.values, label=strategy_label, linewidth=1.5)
    if bench is not None and not bench.empty:
        bench_vol = bench.rolling(window=win, min_periods=min_periods).std(ddof=1) * np.sqrt(
            max(periods_per_year, 1)
        )
        ax.plot(bench_vol.index, bench_vol.values, label=benchmark_label, linewidth=1.4, alpha=0.85)
    ax.set_title(f"{title} ({win}-period)")
    ax.set_ylabel("Volatility")
    ax.legend(loc="best")
    _render_note(fig, None, default_bottom=0.03)
    return _save_or_show(fig, show=show, savefig=savefig)


def rolling_sortino(
    returns: pd.Series,
    *,
    window: int = 63,
    rf: float = 0.0,
    periods_per_year: int = 252,
    title: str = "Rolling Sortino",
    show: bool = True,
    savefig: dict[str, Any] | None = None,
) -> plt.Figure:
    ret = utils.to_series(returns).dropna()
    ret = utils.ensure_datetime_index(ret)
    rf_period = rf / max(periods_per_year, 1)
    fig, ax = plt.subplots(figsize=(10, 3.3))
    if ret.empty:
        ax.set_title(f"{title} (No data)")
        return _save_or_show(fig, show=show, savefig=savefig)

    win, min_periods = _rolling_window(window, len(ret))
    excess = ret - rf_period
    downside = excess.where(excess < 0)
    roll_mean = excess.rolling(window=win, min_periods=min_periods).mean()
    roll_downside = downside.rolling(window=win, min_periods=min_periods).std(ddof=1)
    ratio = roll_mean / roll_downside * np.sqrt(max(periods_per_year, 1))
    ratio = ratio.replace([float("inf"), float("-inf")], pd.NA)

    ax.plot(ratio.index, ratio.values, linewidth=1.5, color="#0ea5e9")
    ax.axhline(0.0, color="#111827", linewidth=1, alpha=0.8)
    ax.set_title(f"{title} ({win}-period)")
    ax.set_ylabel("Sortino")
    _render_note(fig, None, default_bottom=0.03)
    return _save_or_show(fig, show=show, savefig=savefig)


def rolling_beta(
    returns: pd.Series,
    benchmark: pd.Series,
    *,
    short_window: int = 63,
    long_window: int = 126,
    title: str = "Rolling Beta to Benchmark",
    show: bool = True,
    savefig: dict[str, Any] | None = None,
) -> plt.Figure:
    strat, bench = _align_returns(returns, benchmark)
    fig, ax = plt.subplots(figsize=(10, 3.3))
    if strat.empty or bench is None or bench.empty:
        ax.set_title(f"{title} (No data)")
        return _save_or_show(fig, show=show, savefig=savefig)

    sw, smin = _rolling_window(short_window, len(strat))
    lw, lmin = _rolling_window(long_window, len(strat))
    short_beta = (
        strat.rolling(window=sw, min_periods=smin).cov(bench)
        / bench.rolling(window=sw, min_periods=smin).var(ddof=1)
    )
    long_beta = (
        strat.rolling(window=lw, min_periods=lmin).cov(bench)
        / bench.rolling(window=lw, min_periods=lmin).var(ddof=1)
    )

    ax.plot(short_beta.index, short_beta.values, label=f"{sw}-period", linewidth=1.5)
    ax.plot(long_beta.index, long_beta.values, label=f"{lw}-period", linewidth=1.4, alpha=0.85)
    ax.axhline(0.0, color="#111827", linewidth=1, alpha=0.8)
    ax.axhline(1.0, color="#ef4444", linewidth=1.1, linestyle="--", alpha=0.8)
    ax.set_title(title)
    ax.set_ylabel("Beta")
    ax.legend(loc="best")
    _render_note(fig, None, default_bottom=0.03)
    return _save_or_show(fig, show=show, savefig=savefig)


def drawdown_periods(
    returns: pd.Series,
    *,
    top: int = 5,
    title: str = "Worst Drawdown Periods",
    show: bool = True,
    savefig: dict[str, Any] | None = None,
) -> plt.Figure:
    ret = utils.to_series(returns).dropna()
    ret = utils.ensure_datetime_index(ret)
    eq = (1.0 + ret).cumprod() - 1.0
    dd_table = stats.top_drawdowns(returns=ret, top=top)

    fig, ax = plt.subplots(figsize=(10, 4))
    if eq.empty:
        ax.set_title(f"{title} (No data)")
        return _save_or_show(fig, show=show, savefig=savefig)

    ax.plot(eq.index, eq.values * 100.0, linewidth=1.7, color="#2563eb")
    for _, row in dd_table.iterrows():
        start = row.get("Started")
        recovered = row.get("Recovered")
        if pd.isna(start):
            continue
        end = eq.index.max() if pd.isna(recovered) else pd.Timestamp(recovered)
        ax.axvspan(pd.Timestamp(start), end, color="#ef4444", alpha=0.13)
    ax.axhline(0.0, color="#111827", linewidth=1, alpha=0.8)
    ax.set_title(title)
    ax.set_ylabel("Cumulative Return (%)")
    _render_note(fig, None, default_bottom=0.03)
    return _save_or_show(fig, show=show, savefig=savefig)


def underwater(
    returns: pd.Series,
    *,
    title: str = "Underwater Plot",
    show: bool = True,
    savefig: dict[str, Any] | None = None,
) -> plt.Figure:
    dd = stats.drawdown_series(returns=returns)
    dd = utils.to_series(dd).dropna()
    dd = utils.ensure_datetime_index(dd)
    fig, ax = plt.subplots(figsize=(10, 3.2))
    if not dd.empty:
        ax.fill_between(dd.index, dd.values * 100.0, 0.0, color="#0ea5e9", alpha=0.35)
        ax.plot(dd.index, dd.values * 100.0, color="#0284c7", linewidth=1.0, alpha=0.9)
    ax.axhline(0.0, color="#111827", linewidth=1, alpha=0.8)
    ax.set_title(title)
    ax.set_ylabel("Drawdown (%)")
    _render_note(fig, None, default_bottom=0.03)
    return _save_or_show(fig, show=show, savefig=savefig)


def return_quantiles(
    returns: pd.Series,
    *,
    title: str = "Return Quantiles",
    show: bool = True,
    savefig: dict[str, Any] | None = None,
) -> plt.Figure:
    ret = utils.to_series(returns).dropna()
    ret = utils.ensure_datetime_index(ret)
    groups: dict[str, pd.Series] = {"Daily": ret}
    groups["Weekly"] = ret.resample("W").apply(lambda x: (1.0 + x).prod() - 1.0)
    groups["Monthly"] = ret.resample("ME").apply(lambda x: (1.0 + x).prod() - 1.0)
    groups["Quarterly"] = ret.resample("QE").apply(lambda x: (1.0 + x).prod() - 1.0)
    groups["Yearly"] = ret.resample("YE").apply(lambda x: (1.0 + x).prod() - 1.0)

    rows: list[dict[str, float | str]] = []
    order = ["Daily", "Weekly", "Monthly", "Quarterly", "Yearly"]
    for label in order:
        data = groups[label].dropna()
        for value in data.tolist():
            rows.append({"Frequency": label, "ReturnPct": float(value) * 100.0})

    fig, ax = plt.subplots(figsize=(10, 4))
    if rows:
        qdf = pd.DataFrame(rows)
        sns.boxplot(data=qdf, x="Frequency", y="ReturnPct", ax=ax)
    ax.axhline(0.0, color="#111827", linewidth=1, alpha=0.8)
    ax.set_title(title)
    ax.set_ylabel("Return (%)")
    _render_note(fig, None, default_bottom=0.03)
    return _save_or_show(fig, show=show, savefig=savefig)
