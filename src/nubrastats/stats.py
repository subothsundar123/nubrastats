from __future__ import annotations

import numpy as np
import pandas as pd

from . import utils


def comp(returns: pd.Series | pd.DataFrame) -> float | pd.Series:
    ret = returns.fillna(0.0)
    return (1.0 + ret).prod(axis=0) - 1.0


def cagr(returns: pd.Series, periods_per_year: int = 252) -> float:
    ret = utils.to_series(returns).dropna()
    if ret.empty:
        return np.nan
    total = float(comp(ret))
    years = max(len(ret) / utils.annualization_factor(periods_per_year), 1.0 / periods_per_year)
    if total <= -1:
        return np.nan
    return (1.0 + total) ** (1.0 / years) - 1.0


def volatility(returns: pd.Series, periods_per_year: int = 252, annualize: bool = True) -> float:
    ret = utils.to_series(returns).dropna()
    if ret.empty:
        return np.nan
    vol = float(ret.std(ddof=1))
    if annualize:
        vol *= np.sqrt(utils.annualization_factor(periods_per_year))
    return vol


def sharpe(returns: pd.Series, rf: float = 0.0, periods_per_year: int = 252) -> float:
    ret = utils.to_series(returns).dropna()
    if ret.empty:
        return np.nan
    rf_period = rf / utils.annualization_factor(periods_per_year)
    excess = ret - rf_period
    denom = excess.std(ddof=1)
    if denom == 0 or np.isnan(denom):
        return np.nan
    return float(excess.mean() / denom * np.sqrt(utils.annualization_factor(periods_per_year)))


def sortino(returns: pd.Series, rf: float = 0.0, periods_per_year: int = 252) -> float:
    ret = utils.to_series(returns).dropna()
    if ret.empty:
        return np.nan
    rf_period = rf / utils.annualization_factor(periods_per_year)
    excess = ret - rf_period
    downside = excess[excess < 0]
    downside_std = downside.std(ddof=1)
    if downside_std == 0 or np.isnan(downside_std):
        return np.nan
    annualizer = np.sqrt(utils.annualization_factor(periods_per_year))
    return float(excess.mean() / downside_std * annualizer)


def drawdown_series(
    returns: pd.Series | None = None,
    equity: pd.Series | None = None,
) -> pd.Series:
    if equity is None and returns is None:
        raise ValueError("Either returns or equity must be provided")
    if equity is None:
        ret = utils.to_series(returns).fillna(0.0)
        equity = utils.to_equity(ret, start_balance=1.0)
    eq = utils.to_series(equity).dropna()
    rolling_max = eq.cummax()
    return eq / rolling_max - 1.0


def max_drawdown(
    returns: pd.Series | None = None,
    equity: pd.Series | None = None,
) -> float:
    dd = drawdown_series(returns=returns, equity=equity)
    if dd.empty:
        return np.nan
    return float(dd.min())


def win_rate_returns(returns: pd.Series) -> float:
    ret = utils.to_series(returns).dropna()
    non_zero = ret[ret != 0]
    if non_zero.empty:
        return np.nan
    return float((non_zero > 0).sum() / len(non_zero))


def _trade_pnl_series(trades: pd.DataFrame) -> pd.Series:
    if "realized_pnl" in trades.columns:
        return pd.to_numeric(trades["realized_pnl"], errors="coerce").dropna()
    if "pnl" in trades.columns:
        return pd.to_numeric(trades["pnl"], errors="coerce").dropna()
    return pd.Series(dtype=float)


def win_rate_trades(trades: pd.DataFrame) -> float:
    pnl = _trade_pnl_series(trades)
    non_zero = pnl[pnl != 0]
    if non_zero.empty:
        return np.nan
    return float((non_zero > 0).sum() / len(non_zero))


def profit_factor(trades: pd.DataFrame) -> float:
    pnl = _trade_pnl_series(trades)
    if pnl.empty:
        return np.nan
    wins = pnl[pnl > 0].sum()
    losses = -pnl[pnl < 0].sum()
    return utils.safe_div(float(wins), float(losses))


def expectancy(trades: pd.DataFrame) -> float:
    pnl = _trade_pnl_series(trades)
    if pnl.empty:
        return np.nan
    return float(pnl.mean())


def summary(
    *,
    returns: pd.Series | None = None,
    equity: pd.Series | None = None,
    trades: pd.DataFrame | None = None,
    rf: float = 0.0,
    periods_per_year: int = 252,
) -> pd.Series:
    if returns is None:
        if equity is None:
            raise ValueError("Either returns or equity must be provided")
        returns = utils.to_series(utils.to_returns(equity))
    ret = utils.to_series(returns).dropna()
    if ret.empty:
        return pd.Series(dtype=float)

    total_return = float(comp(ret))
    out = {
        "Total Return": total_return,
        "CAGR": cagr(ret, periods_per_year=periods_per_year),
        "Volatility": volatility(ret, periods_per_year=periods_per_year, annualize=True),
        "Sharpe": sharpe(ret, rf=rf, periods_per_year=periods_per_year),
        "Sortino": sortino(ret, rf=rf, periods_per_year=periods_per_year),
        "Max Drawdown": max_drawdown(returns=ret),
        "Win Rate (Periods)": win_rate_returns(ret),
        "Avg Return": float(ret.mean()),
        "Best Period": float(ret.max()),
        "Worst Period": float(ret.min()),
    }

    if trades is not None and not trades.empty:
        out["Win Rate (Trades)"] = win_rate_trades(trades)
        out["Profit Factor"] = profit_factor(trades)
        out["Expectancy"] = expectancy(trades)
        out["Trade Count"] = int(len(_trade_pnl_series(trades)))

    return pd.Series(out)


def downside_deviation(
    returns: pd.Series,
    rf: float = 0.0,
    periods_per_year: int = 252,
    annualize: bool = True,
) -> float:
    ret = utils.to_series(returns).dropna()
    if ret.empty:
        return np.nan
    rf_period = rf / utils.annualization_factor(periods_per_year)
    downside = (ret - rf_period)[(ret - rf_period) < 0]
    if downside.empty:
        return 0.0
    dd = float(downside.std(ddof=1))
    if annualize:
        dd *= np.sqrt(utils.annualization_factor(periods_per_year))
    return dd


def calmar(returns: pd.Series, periods_per_year: int = 252) -> float:
    ret = utils.to_series(returns).dropna()
    if ret.empty:
        return np.nan
    mdd = abs(max_drawdown(returns=ret))
    if mdd == 0 or np.isnan(mdd):
        return np.nan
    return float(cagr(ret, periods_per_year=periods_per_year) / mdd)


def skew(returns: pd.Series) -> float:
    ret = utils.to_series(returns).dropna()
    if ret.empty:
        return np.nan
    return float(ret.skew())


def kurtosis(returns: pd.Series) -> float:
    ret = utils.to_series(returns).dropna()
    if ret.empty:
        return np.nan
    return float(ret.kurtosis())


def value_at_risk(returns: pd.Series, cutoff: float = 0.05) -> float:
    ret = utils.to_series(returns).dropna()
    if ret.empty:
        return np.nan
    return float(ret.quantile(cutoff))


def conditional_value_at_risk(returns: pd.Series, cutoff: float = 0.05) -> float:
    ret = utils.to_series(returns).dropna()
    if ret.empty:
        return np.nan
    var = ret.quantile(cutoff)
    tail = ret[ret <= var]
    if tail.empty:
        return np.nan
    return float(tail.mean())


def correlation(returns: pd.Series, benchmark: pd.Series) -> float:
    strat = utils.to_series(returns).dropna()
    bench = utils.to_series(benchmark).dropna()
    aligned = pd.concat([strat, bench], axis=1, join="inner").dropna()
    if aligned.empty:
        return np.nan
    return float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1]))


def beta(returns: pd.Series, benchmark: pd.Series) -> float:
    strat = utils.to_series(returns).dropna()
    bench = utils.to_series(benchmark).dropna()
    aligned = pd.concat([strat, bench], axis=1, join="inner").dropna()
    if aligned.empty:
        return np.nan
    cov = float(aligned.iloc[:, 0].cov(aligned.iloc[:, 1]))
    var = float(aligned.iloc[:, 1].var(ddof=1))
    return utils.safe_div(cov, var)


def alpha(
    returns: pd.Series,
    benchmark: pd.Series,
    periods_per_year: int = 252,
) -> float:
    strat = utils.to_series(returns).dropna()
    bench = utils.to_series(benchmark).dropna()
    aligned = pd.concat([strat, bench], axis=1, join="inner").dropna()
    if aligned.empty:
        return np.nan
    b = beta(aligned.iloc[:, 0], aligned.iloc[:, 1])
    if np.isnan(b):
        return np.nan
    ann = utils.annualization_factor(periods_per_year)
    return float((aligned.iloc[:, 0].mean() - b * aligned.iloc[:, 1].mean()) * ann)


def information_ratio(
    returns: pd.Series,
    benchmark: pd.Series,
    periods_per_year: int = 252,
) -> float:
    strat = utils.to_series(returns).dropna()
    bench = utils.to_series(benchmark).dropna()
    aligned = pd.concat([strat, bench], axis=1, join="inner").dropna()
    if aligned.empty:
        return np.nan
    active = aligned.iloc[:, 0] - aligned.iloc[:, 1]
    te = active.std(ddof=1)
    if te == 0 or np.isnan(te):
        return np.nan
    return float(active.mean() / te * np.sqrt(utils.annualization_factor(periods_per_year)))


def yearly_returns(returns: pd.Series) -> pd.Series:
    ret = utils.to_series(returns).dropna()
    ret = utils.ensure_datetime_index(ret)
    if ret.empty:
        return pd.Series(dtype=float)
    return ret.groupby(ret.index.year).apply(lambda x: float((1.0 + x).prod() - 1.0))


def _subset_return(subset: pd.Series) -> float:
    part = utils.to_series(subset).dropna()
    if part.empty:
        return np.nan
    return float((1.0 + part).prod() - 1.0)


def _slice_since(returns: pd.Series, since: pd.Timestamp) -> pd.Series:
    ret = utils.to_series(returns).dropna()
    ret = utils.ensure_datetime_index(ret)
    return ret[ret.index >= since]


def trailing_return(
    returns: pd.Series,
    *,
    years: int | None = None,
    months: int | None = None,
    annualized: bool = False,
    periods_per_year: int = 252,
) -> float:
    ret = utils.to_series(returns).dropna()
    ret = utils.ensure_datetime_index(ret)
    if ret.empty:
        return np.nan

    end = ret.index.max()
    since = end
    if years is not None:
        since = since - pd.DateOffset(years=max(int(years), 0))
    if months is not None:
        since = since - pd.DateOffset(months=max(int(months), 0))
    window = ret[ret.index >= since]
    if window.empty:
        return np.nan

    if annualized:
        return cagr(window, periods_per_year=periods_per_year)
    return _subset_return(window)


def month_to_date_return(returns: pd.Series) -> float:
    ret = utils.to_series(returns).dropna()
    ret = utils.ensure_datetime_index(ret)
    if ret.empty:
        return np.nan
    end = ret.index.max()
    start = pd.Timestamp(year=end.year, month=end.month, day=1)
    return _subset_return(_slice_since(ret, start))


def year_to_date_return(returns: pd.Series) -> float:
    ret = utils.to_series(returns).dropna()
    ret = utils.ensure_datetime_index(ret)
    if ret.empty:
        return np.nan
    end = ret.index.max()
    start = pd.Timestamp(year=end.year, month=1, day=1)
    return _subset_return(_slice_since(ret, start))


def top_drawdowns(
    *,
    returns: pd.Series | None = None,
    equity: pd.Series | None = None,
    top: int = 10,
) -> pd.DataFrame:
    dd = drawdown_series(returns=returns, equity=equity)
    dd = utils.to_series(dd).dropna()
    dd = utils.ensure_datetime_index(dd)
    if dd.empty:
        return pd.DataFrame(columns=["Started", "Valley", "Recovered", "Drawdown", "Days"])

    episodes: list[dict[str, object]] = []
    in_dd = False
    start_ts: pd.Timestamp | None = None
    valley_ts: pd.Timestamp | None = None
    valley_val = 0.0

    for ts, value in dd.items():
        val = float(value)
        if not in_dd and val < 0:
            in_dd = True
            start_ts = pd.Timestamp(ts)
            valley_ts = pd.Timestamp(ts)
            valley_val = val
            continue

        if in_dd:
            if val < valley_val:
                valley_val = val
                valley_ts = pd.Timestamp(ts)
            if val >= 0:
                recovered = pd.Timestamp(ts)
                assert start_ts is not None and valley_ts is not None
                episodes.append(
                    {
                        "Started": start_ts,
                        "Valley": valley_ts,
                        "Recovered": recovered,
                        "Drawdown": valley_val,
                        "Days": int((recovered - start_ts).days),
                    }
                )
                in_dd = False
                start_ts = None
                valley_ts = None
                valley_val = 0.0

    if in_dd and start_ts is not None and valley_ts is not None:
        end_ts = pd.Timestamp(dd.index.max())
        episodes.append(
            {
                "Started": start_ts,
                "Valley": valley_ts,
                "Recovered": pd.NaT,
                "Drawdown": valley_val,
                "Days": int((end_ts - start_ts).days),
            }
        )

    if not episodes:
        return pd.DataFrame(columns=["Started", "Valley", "Recovered", "Drawdown", "Days"])

    out = pd.DataFrame(episodes).sort_values("Drawdown", ascending=True)
    out = out.head(max(int(top), 1)).reset_index(drop=True)
    return out
