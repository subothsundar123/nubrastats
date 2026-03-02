from __future__ import annotations

import base64
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from jinja2 import Template
from tabulate import tabulate

from . import plots, stats, utils


def _benchmark_equity_from_returns(benchmark: pd.Series | None) -> pd.Series | None:
    if benchmark is None:
        return None
    bench_ret = utils.to_series(benchmark).dropna()
    if bench_ret.empty:
        return bench_ret
    bench_eq = utils.to_series(utils.to_equity(bench_ret, start_balance=100000.0)).dropna()
    bench_eq = bench_eq[~bench_eq.index.duplicated(keep="last")].sort_index()
    return bench_eq


def _to_metrics_df(
    *,
    returns: pd.Series | None,
    equity: pd.Series | None,
    trades: pd.DataFrame | None,
    benchmark: pd.Series | None = None,
    strategy_label: str = "Strategy",
    benchmark_label: str = "Benchmark",
    rf: float = 0.06,
    periods_per_year: int = 252,
) -> pd.DataFrame:
    strategy = stats.summary(
        returns=returns,
        equity=equity,
        trades=trades,
        rf=rf,
        periods_per_year=periods_per_year,
    )
    if strategy.empty:
        return pd.DataFrame()

    strategy_name = strategy_label.strip() or "Strategy"
    bench_name = benchmark_label.strip() or "Benchmark"

    out = pd.DataFrame({strategy_name: strategy})
    if benchmark is not None:
        bench = stats.summary(
            returns=benchmark,
            equity=None,
            trades=None,
            rf=rf,
            periods_per_year=periods_per_year,
        )
        out[bench_name] = bench.reindex(out.index)
    return out


def metrics(
    *,
    returns: pd.Series | None = None,
    equity: pd.Series | None = None,
    trades: pd.DataFrame | None = None,
    benchmark: pd.Series | None = None,
    strategy_label: str = "Strategy",
    benchmark_label: str = "Benchmark",
    rf: float = 0.06,
    periods_per_year: int = 252,
    display: bool = True,
    precision: int = 4,
) -> pd.DataFrame:
    df = _to_metrics_df(
        returns=returns,
        equity=equity,
        trades=trades,
        benchmark=benchmark,
        strategy_label=strategy_label,
        benchmark_label=benchmark_label,
        rf=rf,
        periods_per_year=periods_per_year,
    )
    if df.empty:
        return df

    formatted = df.copy()
    formatted = formatted.round(precision)
    if display:
        print(tabulate(formatted, headers="keys", tablefmt="simple"))
    return formatted


def basic(
    *,
    returns: pd.Series | None = None,
    equity: pd.Series | None = None,
    trades: pd.DataFrame | None = None,
    benchmark: pd.Series | None = None,
    strategy_label: str = "Strategy",
    benchmark_label: str = "Benchmark",
    rf: float = 0.06,
    periods_per_year: int = 252,
    display: bool = True,
    show_plots: bool = True,
) -> pd.DataFrame:
    df = metrics(
        returns=returns,
        equity=equity,
        trades=trades,
        benchmark=benchmark,
        strategy_label=strategy_label,
        benchmark_label=benchmark_label,
        rf=rf,
        periods_per_year=periods_per_year,
        display=display,
    )
    if show_plots:
        benchmark_equity = _benchmark_equity_from_returns(benchmark)
        if equity is None and returns is not None:
            equity = utils.to_series(utils.to_equity(returns, start_balance=100000.0))
        if equity is not None:
            plots.equity_curve(equity, benchmark=benchmark_equity, show=True)
            plots.drawdown(equity=equity, show=True)
        if returns is not None:
            plots.monthly_heatmap(returns, show=True)
    return df


def full(
    *,
    returns: pd.Series | None = None,
    equity: pd.Series | None = None,
    trades: pd.DataFrame | None = None,
    benchmark: pd.Series | None = None,
    strategy_label: str = "Strategy",
    benchmark_label: str = "Benchmark",
    rf: float = 0.06,
    periods_per_year: int = 252,
    display: bool = True,
    show_plots: bool = True,
) -> pd.DataFrame:
    df = basic(
        returns=returns,
        equity=equity,
        trades=trades,
        benchmark=benchmark,
        strategy_label=strategy_label,
        benchmark_label=benchmark_label,
        rf=rf,
        periods_per_year=periods_per_year,
        display=display,
        show_plots=False,
    )
    if show_plots:
        benchmark_equity = _benchmark_equity_from_returns(benchmark)
        if returns is not None:
            plots.rolling_sharpe(returns, rf=rf, periods_per_year=periods_per_year, show=True)
            plots.monthly_heatmap(returns, show=True)
        if equity is not None:
            plots.equity_curve(equity, benchmark=benchmark_equity, show=True)
            plots.drawdown(equity=equity, show=True)
        if trades is not None and not trades.empty:
            plots.pnl_distribution(trades, show=True)
    return df


def _embed_figure_png(fig) -> str:
    data = plots.figure_to_png_bytes(fig)
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def _html_basic(
    *,
    returns: pd.Series | None = None,
    equity: pd.Series | None = None,
    trades: pd.DataFrame | None = None,
    benchmark: pd.Series | None = None,
    strategy_label: str = "Strategy",
    benchmark_label: str = "Benchmark",
    rf: float = 0.06,
    periods_per_year: int = 252,
    title: str = "Nubra Strategy Tearsheet",
    output: str | None = None,
    template_path: str | None = None,
) -> str:
    if returns is None:
        if equity is None:
            raise ValueError("Either returns or equity must be provided")
        returns = utils.to_series(utils.to_returns(equity))
    if equity is None:
        equity = utils.to_series(utils.to_equity(returns, start_balance=100000.0))

    mdf = _to_metrics_df(
        returns=returns,
        equity=equity,
        trades=trades,
        benchmark=benchmark,
        strategy_label=strategy_label,
        benchmark_label=benchmark_label,
        rf=rf,
        periods_per_year=periods_per_year,
    )
    if mdf.empty:
        raise ValueError("No data available to generate report")

    date_start = str(utils.to_series(returns).index.min())
    date_end = str(utils.to_series(returns).index.max())

    strategy_name = strategy_label.strip() or "Strategy"
    bench_name = benchmark_label.strip() or "Benchmark"
    compared_name = bench_name if benchmark is not None else None
    benchmark_equity = _benchmark_equity_from_returns(benchmark)

    eq_title = f"Equity Curve - {strategy_name}"
    if compared_name:
        eq_title += f" vs {compared_name}"

    fig_eq = plots.equity_curve(equity, benchmark=benchmark_equity, title=eq_title, show=False)
    fig_dd = plots.drawdown(equity=equity, title=f"Drawdown - {strategy_name}", show=False)
    fig_heat = plots.monthly_heatmap(
        returns,
        title=f"Monthly Returns Heatmap - {strategy_name}",
        show=False,
    )
    fig_sharpe = plots.rolling_sharpe(
        returns,
        rf=rf,
        periods_per_year=periods_per_year,
        title=f"Rolling Sharpe - {strategy_name}",
        show=False,
    )
    pnl_img = ""
    if trades is not None and not trades.empty:
        fig_pnl = plots.pnl_distribution(trades, show=False)
        pnl_img = _embed_figure_png(fig_pnl)

    if isinstance(mdf, pd.Series):
        metrics_html = mdf.round(4).to_frame().to_html()
    else:
        metrics_html = mdf.round(4).to_html()
    if template_path is None:
        template_path = str(Path(__file__).parent / "templates" / "report.html")
    tpl = Template(Path(template_path).read_text(encoding="utf-8"))

    html_string = tpl.render(
        title=title,
        date_start=date_start,
        date_end=date_end,
        strategy_label=strategy_name,
        benchmark_label=compared_name,
        metrics_table=metrics_html,
        equity_img=_embed_figure_png(fig_eq),
        drawdown_img=_embed_figure_png(fig_dd),
        heatmap_img=_embed_figure_png(fig_heat),
        sharpe_img=_embed_figure_png(fig_sharpe),
        pnl_img=pnl_img,
    )

    output_path = output or "nubrastats-report.html"
    Path(output_path).write_text(html_string, encoding="utf-8")
    return output_path


def _fmt_value(value: object, style: str = "num") -> str:
    if value is None:
        return "-"
    if isinstance(value, (float, np.floating)) and (np.isnan(value) or np.isinf(value)):
        return "-"
    if pd.isna(value):
        return "-"
    if style == "pct":
        return f"{float(value) * 100.0:.2f}%"
    if style == "int":
        return f"{int(round(float(value)))}"
    if style == "date":
        stamp = pd.Timestamp(value)
        return stamp.strftime("%Y-%m-%d")
    return f"{float(value):.3f}"


def _build_key_metrics_table(
    *,
    returns: pd.Series,
    benchmark: pd.Series | None,
    strategy_label: str,
    benchmark_label: str | None,
    rf: float,
    periods_per_year: int,
) -> pd.DataFrame:
    ret = utils.to_series(returns).dropna()
    bench = utils.to_series(benchmark).dropna() if benchmark is not None else None

    rows: list[tuple[str, str, float | pd.Timestamp | None, float | pd.Timestamp | None]] = []
    rows.append(("Risk-Free Rate", "pct", rf, rf if bench is not None else None))
    rows.append(
        (
            "Total Return",
            "pct",
            float(stats.comp(ret)),
            float(stats.comp(bench)) if bench is not None else None,
        )
    )
    rows.append(
        (
            "CAGR",
            "pct",
            stats.cagr(ret, periods_per_year=periods_per_year),
            (
                stats.cagr(bench, periods_per_year=periods_per_year)
                if bench is not None
                else None
            ),
        )
    )
    rows.append(
        (
            "Volatility (ann.)",
            "pct",
            stats.volatility(ret, periods_per_year=periods_per_year),
            (
                stats.volatility(bench, periods_per_year=periods_per_year)
                if bench is not None
                else None
            ),
        )
    )
    rows.append(
        (
            "Sharpe",
            "num",
            stats.sharpe(ret, rf=rf, periods_per_year=periods_per_year),
            (
                stats.sharpe(bench, rf=rf, periods_per_year=periods_per_year)
                if bench is not None
                else None
            ),
        )
    )
    rows.append(
        (
            "Sortino",
            "num",
            stats.sortino(ret, rf=rf, periods_per_year=periods_per_year),
            (
                stats.sortino(bench, rf=rf, periods_per_year=periods_per_year)
                if bench is not None
                else None
            ),
        )
    )
    rows.append(
        (
            "Calmar",
            "num",
            stats.calmar(ret, periods_per_year=periods_per_year),
            (
                stats.calmar(bench, periods_per_year=periods_per_year)
                if bench is not None
                else None
            ),
        )
    )
    rows.append(
        (
            "Max Drawdown",
            "pct",
            stats.max_drawdown(returns=ret),
            stats.max_drawdown(returns=bench) if bench is not None else None,
        )
    )
    rows.append(
        (
            "Avg Return",
            "pct",
            float(ret.mean()) if not ret.empty else np.nan,
            (
                float(bench.mean())
                if bench is not None and not bench.empty
                else np.nan
            ),
        )
    )
    rows.append(
        (
            "Best Day",
            "pct",
            float(ret.max()) if not ret.empty else np.nan,
            (
                float(bench.max())
                if bench is not None and not bench.empty
                else np.nan
            ),
        )
    )
    rows.append(
        (
            "Worst Day",
            "pct",
            float(ret.min()) if not ret.empty else np.nan,
            (
                float(bench.min())
                if bench is not None and not bench.empty
                else np.nan
            ),
        )
    )
    rows.append(
        (
            "Value-at-Risk (95%)",
            "pct",
            stats.value_at_risk(ret),
            stats.value_at_risk(bench) if bench is not None else None,
        )
    )
    rows.append(
        (
            "Expected Shortfall (CVaR)",
            "pct",
            stats.conditional_value_at_risk(ret),
            stats.conditional_value_at_risk(bench) if bench is not None else None,
        )
    )
    rows.append(("Skew", "num", stats.skew(ret), stats.skew(bench) if bench is not None else None))
    rows.append(
        (
            "Kurtosis",
            "num",
            stats.kurtosis(ret),
            stats.kurtosis(bench) if bench is not None else None,
        )
    )

    if bench is not None and not bench.empty:
        rows.extend(
            [
                ("Beta (vs Benchmark)", "num", stats.beta(ret, bench), None),
                (
                    "Alpha (ann.)",
                    "pct",
                    stats.alpha(ret, bench, periods_per_year=periods_per_year),
                    None,
                ),
                ("Correlation", "pct", stats.correlation(ret, bench), None),
                (
                    "Information Ratio",
                    "num",
                    stats.information_ratio(
                        ret,
                        bench,
                        periods_per_year=periods_per_year,
                    ),
                    None,
                ),
            ]
        )

    if bench is not None and benchmark_label:
        columns = [strategy_label, benchmark_label]
    else:
        columns = [strategy_label]

    records: list[dict[str, str]] = []
    for metric, style, strat_val, bench_val in rows:
        row: dict[str, str] = {"Metric": metric, strategy_label: _fmt_value(strat_val, style)}
        if bench is not None and benchmark_label:
            row[benchmark_label] = _fmt_value(bench_val, style)
        records.append(row)

    table = pd.DataFrame(records).set_index("Metric")
    return table[columns]


def _build_period_table(
    *,
    returns: pd.Series,
    benchmark: pd.Series | None,
    strategy_label: str,
    benchmark_label: str | None,
    periods_per_year: int,
) -> pd.DataFrame:
    ret = utils.to_series(returns).dropna()
    bench = utils.to_series(benchmark).dropna() if benchmark is not None else None

    period_specs: list[tuple[str, dict[str, object], str]] = [
        ("MTD", {}, "mtd"),
        ("3M", {"months": 3}, "raw"),
        ("6M", {"months": 6}, "raw"),
        ("YTD", {}, "ytd"),
        ("1Y", {"years": 1}, "raw"),
        ("3Y (ann.)", {"years": 3}, "ann"),
        ("5Y (ann.)", {"years": 5}, "ann"),
        ("All-time (ann.)", {}, "all_ann"),
    ]

    rows: list[dict[str, str]] = []
    for label, kwargs, mode in period_specs:
        if mode == "mtd":
            strat_val = stats.month_to_date_return(ret)
            bench_val = stats.month_to_date_return(bench) if bench is not None else None
        elif mode == "ytd":
            strat_val = stats.year_to_date_return(ret)
            bench_val = stats.year_to_date_return(bench) if bench is not None else None
        elif mode == "ann":
            strat_val = stats.trailing_return(
                ret,
                annualized=True,
                periods_per_year=periods_per_year,
                **kwargs,
            )
            bench_val = (
                stats.trailing_return(
                    bench,
                    annualized=True,
                    periods_per_year=periods_per_year,
                    **kwargs,
                )
                if bench is not None
                else None
            )
        elif mode == "all_ann":
            strat_val = stats.cagr(ret, periods_per_year=periods_per_year)
            bench_val = (
                stats.cagr(bench, periods_per_year=periods_per_year)
                if bench is not None
                else None
            )
        else:
            strat_val = stats.trailing_return(ret, annualized=False, **kwargs)
            bench_val = (
                stats.trailing_return(bench, annualized=False, **kwargs)
                if bench is not None
                else None
            )

        row: dict[str, str] = {"Period": label, strategy_label: _fmt_value(strat_val, "pct")}
        if bench is not None and benchmark_label:
            row[benchmark_label] = _fmt_value(bench_val, "pct")
        rows.append(row)

    table = pd.DataFrame(rows).set_index("Period")
    if bench is not None and benchmark_label:
        return table[[strategy_label, benchmark_label]]
    return table[[strategy_label]]


def _build_eoy_table(
    *,
    returns: pd.Series,
    benchmark: pd.Series | None,
    strategy_label: str,
    benchmark_label: str | None,
) -> pd.DataFrame:
    strat_year = stats.yearly_returns(returns)
    bench_year = (
        stats.yearly_returns(benchmark)
        if benchmark is not None
        else pd.Series(dtype=float)
    )
    years = sorted(set(strat_year.index.tolist()) | set(bench_year.index.tolist()))
    if not years:
        return pd.DataFrame()

    records: list[dict[str, str]] = []
    for y in years:
        strat_val = float(strat_year.get(y, np.nan))
        row: dict[str, str] = {"Year": str(y), strategy_label: _fmt_value(strat_val, "pct")}
        if benchmark is not None and benchmark_label:
            bench_val = float(bench_year.get(y, np.nan))
            multiplier = np.nan
            if not np.isnan(bench_val) and bench_val != 0:
                multiplier = strat_val / bench_val
            row[benchmark_label] = _fmt_value(bench_val, "pct")
            row["Multiplier"] = _fmt_value(multiplier, "num")
            if np.isnan(strat_val) or np.isnan(bench_val):
                row["Won"] = "-"
            else:
                row["Won"] = "+" if strat_val > bench_val else "-"
        records.append(row)

    table = pd.DataFrame(records).set_index("Year")
    if benchmark is not None and benchmark_label:
        return table[[benchmark_label, strategy_label, "Multiplier", "Won"]]
    return table[[strategy_label]]


def _build_drawdown_table(returns: pd.Series, *, top: int = 10) -> pd.DataFrame:
    dd = stats.top_drawdowns(returns=returns, top=top)
    if dd.empty:
        return pd.DataFrame(columns=["Started", "Recovered", "Drawdown", "Days"])
    out = dd.copy()
    out["Started"] = out["Started"].apply(lambda v: _fmt_value(v, "date"))
    out["Recovered"] = out["Recovered"].apply(lambda v: _fmt_value(v, "date"))
    out["Drawdown"] = out["Drawdown"].apply(lambda v: _fmt_value(v, "pct"))
    out["Days"] = out["Days"].apply(lambda v: _fmt_value(v, "int"))
    return out[["Started", "Recovered", "Drawdown", "Days"]]


def _html_detailed(
    *,
    returns: pd.Series | None = None,
    equity: pd.Series | None = None,
    trades: pd.DataFrame | None = None,
    benchmark: pd.Series | None = None,
    strategy_label: str = "Strategy",
    benchmark_label: str = "Benchmark",
    rf: float = 0.06,
    periods_per_year: int = 252,
    title: str = "Nubra Detailed Tearsheet",
    output: str | None = None,
    template_path: str | None = None,
    rolling_window: int = 63,
    top_drawdowns: int = 10,
) -> str:
    if returns is None:
        if equity is None:
            raise ValueError("Either returns or equity must be provided")
        returns = utils.to_series(utils.to_returns(equity))
    returns = utils.to_series(returns).dropna()
    returns = utils.ensure_datetime_index(returns)
    if returns.empty:
        raise ValueError("No returns data available to generate detailed report")

    if equity is None:
        equity = utils.to_series(utils.to_equity(returns, start_balance=100000.0))
    equity = utils.to_series(equity).dropna()
    equity = utils.ensure_datetime_index(equity)

    strategy_name = strategy_label.strip() or "Strategy"
    compared_name = benchmark_label.strip() if benchmark is not None else None
    bench_ret = None
    if benchmark is not None:
        bench_ret = utils.to_series(benchmark).dropna()
        bench_ret = utils.ensure_datetime_index(bench_ret)

    key_table = _build_key_metrics_table(
        returns=returns,
        benchmark=bench_ret,
        strategy_label=strategy_name,
        benchmark_label=compared_name,
        rf=rf,
        periods_per_year=periods_per_year,
    )
    period_table = _build_period_table(
        returns=returns,
        benchmark=bench_ret,
        strategy_label=strategy_name,
        benchmark_label=compared_name,
        periods_per_year=periods_per_year,
    )
    eoy_table = _build_eoy_table(
        returns=returns,
        benchmark=bench_ret,
        strategy_label=strategy_name,
        benchmark_label=compared_name,
    )
    dd_table = _build_drawdown_table(returns, top=top_drawdowns)

    fig_returns = plots.cumulative_returns(
        returns,
        benchmark=bench_ret,
        title="Cumulative Returns vs Benchmark",
        strategy_label=strategy_name,
        benchmark_label=compared_name or "Benchmark",
        show=False,
    )
    fig_log_returns = plots.cumulative_returns(
        returns,
        benchmark=bench_ret,
        title="Cumulative Returns vs Benchmark (Log Scaled)",
        strategy_label=strategy_name,
        benchmark_label=compared_name or "Benchmark",
        log_scale=True,
        show=False,
    )
    fig_vol_match = None
    if bench_ret is not None:
        fig_vol_match = plots.cumulative_returns(
            returns,
            benchmark=bench_ret,
            title="Cumulative Returns vs Benchmark (Volatility Matched)",
            strategy_label=strategy_name,
            benchmark_label=compared_name or "Benchmark",
            match_volatility=True,
            show=False,
        )

    fig_eoy = plots.yearly_returns(
        returns,
        benchmark=bench_ret,
        title="EOY Returns vs Benchmark",
        strategy_label=strategy_name,
        benchmark_label=compared_name or "Benchmark",
        show=False,
    )
    fig_dist = plots.returns_distribution(
        returns,
        benchmark=bench_ret,
        title="Distribution of Monthly Returns",
        strategy_label=strategy_name,
        benchmark_label=compared_name or "Benchmark",
        show=False,
    )
    fig_daily = plots.daily_active_returns(returns, title="Daily Active Returns", show=False)
    fig_roll_vol = plots.rolling_volatility(
        returns,
        benchmark=bench_ret,
        window=rolling_window,
        periods_per_year=periods_per_year,
        title="Rolling Volatility",
        strategy_label=strategy_name,
        benchmark_label=compared_name or "Benchmark",
        show=False,
    )
    fig_roll_sharpe = plots.rolling_sharpe(
        returns,
        window=rolling_window,
        rf=rf,
        periods_per_year=periods_per_year,
        title="Rolling Sharpe",
        show=False,
    )
    fig_roll_sortino = plots.rolling_sortino(
        returns,
        window=rolling_window,
        rf=rf,
        periods_per_year=periods_per_year,
        title="Rolling Sortino",
        show=False,
    )
    fig_roll_beta = None
    if bench_ret is not None:
        fig_roll_beta = plots.rolling_beta(
            returns,
            bench_ret,
            short_window=max(rolling_window, 20),
            long_window=max(rolling_window * 2, rolling_window + 10),
            title="Rolling Beta to Benchmark",
            show=False,
        )
    fig_dd_periods = plots.drawdown_periods(
        returns,
        top=max(top_drawdowns // 2, 3),
        title=f"{strategy_name} - Worst Drawdown Periods",
        show=False,
    )
    fig_underwater = plots.underwater(returns, title="Underwater Plot", show=False)
    fig_heat = plots.monthly_heatmap(
        returns,
        title=f"{strategy_name} - Monthly Active Returns (%)",
        show=False,
    )
    fig_quantiles = plots.return_quantiles(
        returns,
        title=f"{strategy_name} - Return Quantiles",
        show=False,
    )

    pnl_img = ""
    if trades is not None and not trades.empty:
        fig_pnl = plots.pnl_distribution(trades, title="Trade PnL Distribution", show=False)
        pnl_img = _embed_figure_png(fig_pnl)

    date_start = str(returns.index.min())
    date_end = str(returns.index.max())

    if template_path is None:
        template_path = str(Path(__file__).parent / "templates" / "report_detailed.html")
    tpl = Template(Path(template_path).read_text(encoding="utf-8"))

    html_string = tpl.render(
        title=title,
        date_start=date_start,
        date_end=date_end,
        strategy_label=strategy_name,
        benchmark_label=compared_name,
        key_metrics_table=key_table.to_html(escape=False),
        periods_table=period_table.to_html(escape=False),
        eoy_table=eoy_table.to_html(escape=False) if not eoy_table.empty else "",
        drawdown_table=dd_table.to_html(index=False, escape=False) if not dd_table.empty else "",
        returns_img=_embed_figure_png(fig_returns),
        log_returns_img=_embed_figure_png(fig_log_returns),
        vol_match_img=_embed_figure_png(fig_vol_match) if fig_vol_match is not None else "",
        eoy_img=_embed_figure_png(fig_eoy),
        dist_img=_embed_figure_png(fig_dist),
        daily_active_img=_embed_figure_png(fig_daily),
        rolling_beta_img=_embed_figure_png(fig_roll_beta) if fig_roll_beta is not None else "",
        rolling_vol_img=_embed_figure_png(fig_roll_vol),
        rolling_sharpe_img=_embed_figure_png(fig_roll_sharpe),
        rolling_sortino_img=_embed_figure_png(fig_roll_sortino),
        drawdown_periods_img=_embed_figure_png(fig_dd_periods),
        underwater_img=_embed_figure_png(fig_underwater),
        heatmap_img=_embed_figure_png(fig_heat),
        quantiles_img=_embed_figure_png(fig_quantiles),
        pnl_img=pnl_img,
    )

    output_path = output or "nubrastats-detailed-report.html"
    Path(output_path).write_text(html_string, encoding="utf-8")
    return output_path


def html(
    *,
    returns: pd.Series | None = None,
    equity: pd.Series | None = None,
    trades: pd.DataFrame | None = None,
    benchmark: pd.Series | None = None,
    strategy_label: str = "Strategy",
    benchmark_label: str = "Benchmark",
    rf: float = 0.06,
    periods_per_year: int = 252,
    title: str = "Nubra Strategy Tearsheet",
    output: str | None = None,
    template_path: str | None = None,
    mode: str = "basic",
    rolling_window: int = 63,
    top_drawdowns: int = 10,
) -> str:
    report_mode = mode.strip().lower()
    if report_mode in {"basic", "simple"}:
        return _html_basic(
            returns=returns,
            equity=equity,
            trades=trades,
            benchmark=benchmark,
            strategy_label=strategy_label,
            benchmark_label=benchmark_label,
            rf=rf,
            periods_per_year=periods_per_year,
            title=title,
            output=output,
            template_path=template_path,
        )
    if report_mode in {"detailed", "full", "advanced"}:
        detailed_title = title if title else "Nubra Detailed Tearsheet"
        return _html_detailed(
            returns=returns,
            equity=equity,
            trades=trades,
            benchmark=benchmark,
            strategy_label=strategy_label,
            benchmark_label=benchmark_label,
            rf=rf,
            periods_per_year=periods_per_year,
            title=detailed_title,
            output=output,
            template_path=template_path,
            rolling_window=rolling_window,
            top_drawdowns=top_drawdowns,
        )
    raise ValueError("mode must be one of: basic, detailed")
