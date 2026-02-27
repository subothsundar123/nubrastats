from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

import nubrastats as ns

NUBRA_INTERVALS = {"1s", "1m", "2m", "3m", "5m", "15m", "30m", "1h", "1d", "1w", "1mt"}
_NUBRA_MARKET_DATA: Any | None = None
_NUBRA_ENV_NAME: str | None = None


@dataclass(frozen=True)
class InstrumentRequest:
    symbol: str
    exchange: str
    instrument_type: str


def print_library_explainer() -> None:
    _line()
    print("What This Library Does (nubrastats)")
    print("1) Fetches price history from Nubra Historical API (close candles).")
    print("2) Converts prices into periodic returns.")
    print("3) Builds an equity curve from returns (base 100000).")
    print("4) Calculates performance metrics and generates plots/reports.")
    print("")
    print("Data Source in this tester:")
    print("- Nubra SDK: MarketData.historical_data(...)")
    print("- Inputs: exchange, instrument type, symbol, interval, start/end date")
    print("")
    print("Transformations:")
    print("- returns[t] = price[t] / price[t-1] - 1")
    print("- equity[t] = equity[t-1] * (1 + returns[t])")
    print("")
    print("Key Metrics (from nubrastats.stats):")
    print("- Total Return = product(1 + returns) - 1")
    print("- CAGR = (1 + total_return)^(1/years) - 1")
    print("- Volatility = std(returns) * sqrt(periods_per_year)")
    print("- Sharpe = mean(excess_returns) / std(excess_returns) * sqrt(periods_per_year)")
    print(
        "- Sortino = mean(excess_returns) / std(negative_excess_returns) * "
        "sqrt(periods_per_year)"
    )
    print("- Drawdown Series = equity / cumulative_max(equity) - 1")
    print("- Max Drawdown = min(drawdown_series)")
    print("- Win Rate (Periods) = count(returns > 0) / count(returns != 0)")
    print("")
    print("Outputs:")
    print("- Metrics table in terminal")
    print("- PNG charts (equity, drawdown, heatmap, rolling sharpe)")
    print("- HTML tearsheet report")


def _line() -> None:
    print("-" * 72)


def _prompt(text: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{text}{suffix}: ").strip()
    if not value and default is not None:
        return default
    return value


def _prompt_yes_no(text: str, default: bool) -> bool:
    default_label = "y" if default else "n"
    while True:
        value = _prompt(f"{text} (y/n)", default_label).lower()
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("Enter y or n.")


def _prompt_choice(title: str, choices: dict[str, str], default: str | None = None) -> str:
    while True:
        _line()
        print(title)
        for key, label in choices.items():
            print(f"{key}. {label}")
        prompt = "Enter choice"
        if default is not None:
            prompt += f" [{default}]"
        choice = input(f"{prompt}: ").strip()
        if not choice and default is not None:
            choice = default
        if choice in choices:
            return choice
        print("Invalid choice. Try again.")


def _prompt_date_range() -> tuple[pd.Timestamp, pd.Timestamp]:
    start_raw = _prompt("Start date (YYYY-MM-DD)", "2025-01-01")
    end_raw = _prompt("End date (YYYY-MM-DD)", date.today().isoformat())
    try:
        start = pd.to_datetime(start_raw).normalize()
        end = pd.to_datetime(end_raw).normalize() + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    except Exception as exc:
        raise ValueError(f"Invalid date input: {exc}") from exc
    if end < start:
        raise ValueError("End date must be greater than or equal to start date.")
    return start, end


def _filter_by_dates(series: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    s = series.copy()
    s.index = pd.to_datetime(s.index)
    return s[(s.index >= start) & (s.index <= end)].sort_index()


def _prompt_interval() -> str:
    default_interval = "1d"
    interval = _prompt(
        "Interval (1s,1m,2m,3m,5m,15m,30m,1h,1d,1w,1mt)",
        default_interval,
    )
    if interval not in NUBRA_INTERVALS:
        raise ValueError(f"Invalid interval: {interval}")
    return interval


def _prompt_instrument_type(default: str = "STOCK") -> str:
    choices = {
        "1": "STOCK",
        "2": "INDEX",
        "3": "OPT",
        "4": "FUT",
    }
    default_upper = default.upper()
    default_key = "1"
    for key, label in choices.items():
        if label == default_upper:
            default_key = key
            break
    picked = _prompt_choice("Choose instrument type", choices, default=default_key)
    return choices[picked]


def _prompt_instrument(label: str, default_type: str) -> InstrumentRequest:
    symbol = _prompt(f"Enter {label} symbol").upper()
    if not symbol:
        raise ValueError(f"{label} symbol cannot be empty.")
    exchange = _prompt(f"Exchange for {symbol}", "NSE").upper()
    instrument_type = _prompt_instrument_type(default=default_type)
    return InstrumentRequest(
        symbol=symbol,
        exchange=exchange,
        instrument_type=instrument_type,
    )


def _to_utc_iso(ts: pd.Timestamp) -> str:
    stamp = pd.Timestamp(ts)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    else:
        stamp = stamp.tz_convert("UTC")
    return stamp.isoformat().replace("+00:00", "Z")


def _get_nubra_market_data_client() -> Any:
    global _NUBRA_MARKET_DATA
    global _NUBRA_ENV_NAME

    if _NUBRA_MARKET_DATA is not None:
        return _NUBRA_MARKET_DATA

    try:
        from nubra_python_sdk.marketdata.market_data import MarketData
        from nubra_python_sdk.start_sdk import InitNubraSdk, NubraEnv
    except ImportError as exc:
        raise ImportError(
            "nubra_python_sdk is not installed. Install Nubra SDK before using this script."
        ) from exc

    env_map = {
        "1": ("UAT", NubraEnv.UAT),
        "2": ("PROD", NubraEnv.PROD),
        "3": ("DEV", NubraEnv.DEV),
        "4": ("STAGING", NubraEnv.STAGING),
    }
    env_choice = _prompt_choice(
        "Select Nubra environment",
        {
            "1": "UAT",
            "2": "PROD",
            "3": "DEV",
            "4": "STAGING",
        },
        default="1",
    )
    env_name, env_value = env_map[env_choice]
    env_creds = _prompt_yes_no("Use .env credentials (env_creds=True)", True)
    totp_login = _prompt_yes_no("Use TOTP login (totp_login=True)", False)

    _line()
    print(f"Initializing Nubra SDK session in {env_name}...")
    nubra = InitNubraSdk(env=env_value, totp_login=totp_login, env_creds=env_creds)
    _NUBRA_MARKET_DATA = MarketData(nubra)
    _NUBRA_ENV_NAME = env_name
    print(f"Nubra session ready in {_NUBRA_ENV_NAME}.")
    return _NUBRA_MARKET_DATA


def _load_nubra_series(
    request: InstrumentRequest,
    start: pd.Timestamp,
    end: pd.Timestamp,
    interval: str,
) -> pd.Series:
    md_client = _get_nubra_market_data_client()
    payload = {
        "exchange": request.exchange,
        "type": request.instrument_type,
        "values": [request.symbol],
        "fields": ["close"],
        "startDate": _to_utc_iso(start),
        "endDate": _to_utc_iso(end),
        "interval": interval,
        "intraDay": False,
        "realTime": False,
    }
    result = md_client.historical_data(payload)

    rows: list[tuple[pd.Timestamp, float]] = []
    for data_block in getattr(result, "result", []) or []:
        for symbol_map in getattr(data_block, "values", []) or []:
            if not isinstance(symbol_map, dict):
                continue
            for symbol_name, field_values in symbol_map.items():
                if str(symbol_name).upper() != request.symbol:
                    continue
                close_points = getattr(field_values, "close", None) or []
                for point in close_points:
                    raw_ts = getattr(point, "timestamp", None)
                    raw_val = getattr(point, "value", None)
                    if raw_ts is None or raw_val is None:
                        continue
                    rows.append((ns.utils.to_timestamp(raw_ts), float(raw_val)))

    if not rows:
        response_message = getattr(result, "message", "No data")
        raise ValueError(
            f"No close data from Nubra for {request.symbol} "
            f"[{request.exchange}/{request.instrument_type}] ({response_message})."
        )

    df = pd.DataFrame(rows, columns=["timestamp", "close"]).dropna()
    df = df.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    series = pd.Series(
        pd.to_numeric(df["close"], errors="coerce").values,
        index=pd.to_datetime(df["timestamp"]),
        name=request.symbol,
    ).dropna()
    series = _filter_by_dates(series, start, end)
    if series.empty:
        raise ValueError(
            f"No rows after date filtering for {request.symbol}. "
            "Check date range and interval."
        )
    _line()
    print("Nubra Historical Data Fetch Summary")
    print(
        f"Env={_NUBRA_ENV_NAME} | Exchange={request.exchange} | "
        f"Type={request.instrument_type} | Symbol={request.symbol} | Interval={interval}"
    )
    print(f"Range: {start} -> {end}")
    print(f"Candles received: {len(series)}")
    print(f"First: {series.index.min()}  close={float(series.iloc[0]):.4f}")
    print(f"Last : {series.index.max()}  close={float(series.iloc[-1]):.4f}")
    return series


def _to_returns_equity(prices: pd.Series) -> tuple[pd.Series, pd.Series]:
    returns = ns.utils.to_series(ns.utils.to_returns(prices)).dropna()
    equity = ns.utils.to_series(ns.utils.to_equity(returns, start_balance=100000.0)).dropna()
    returns = returns[~returns.index.duplicated(keep="last")].sort_index()
    equity = equity[~equity.index.duplicated(keep="last")].sort_index()
    _line()
    print("Transformation Summary")
    print("Step 1: prices -> returns using pct_change")
    print("Step 2: returns -> equity using cumulative compounding from 100000")
    print(f"Return rows: {len(returns)} | Equity rows: {len(equity)}")
    if not returns.empty:
        print(
            f"Return sample: first={float(returns.iloc[0]):.6f}, "
            f"last={float(returns.iloc[-1]):.6f}"
        )
    if not equity.empty:
        print(
            f"Equity sample: first={float(equity.iloc[0]):.2f}, "
            f"last={float(equity.iloc[-1]):.2f}"
        )
    return returns, equity


def _ensure_output_dir() -> Path:
    out_dir = Path(_prompt("Output folder for reports/plots", "test_outputs"))
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _save_basic_plots(symbol: str, returns: pd.Series, equity: pd.Series, out_dir: Path) -> None:
    ns.plots.equity_curve(
        equity,
        title=f"{symbol} Equity Curve",
        show=False,
        savefig={"fname": str(out_dir / f"{symbol}_equity.png")},
    )
    ns.plots.drawdown(
        equity=equity,
        title=f"{symbol} Drawdown",
        show=False,
        savefig={"fname": str(out_dir / f"{symbol}_drawdown.png")},
    )
    ns.plots.monthly_heatmap(
        returns,
        title=f"{symbol} Monthly Returns",
        show=False,
        savefig={"fname": str(out_dir / f"{symbol}_heatmap.png")},
    )
    ns.plots.rolling_sharpe(
        returns,
        title=f"{symbol} Rolling Sharpe",
        show=False,
        savefig={"fname": str(out_dir / f"{symbol}_rolling_sharpe.png")},
    )


def run_single_symbol() -> None:
    _line()
    print("Single Symbol Analysis")
    symbol_req = _prompt_instrument("primary", default_type="STOCK")
    start, end = _prompt_date_range()
    interval = _prompt_interval()
    prices = _load_nubra_series(symbol_req, start, end, interval)
    returns, equity = _to_returns_equity(prices)

    _line()
    print(f"Metrics for {symbol_req.symbol}")
    ns.reports.metrics(returns=returns, display=True)

    save = _prompt("Save plots as PNG? (y/n)", "y").lower()
    if save == "y":
        out_dir = _ensure_output_dir()
        _save_basic_plots(symbol_req.symbol, returns, equity, out_dir)
        print(f"Saved plots in: {out_dir.resolve()}")


def run_compare_symbols() -> None:
    _line()
    print("Symbol vs Benchmark Comparison")
    primary_req = _prompt_instrument("primary", default_type="STOCK")
    benchmark_req = _prompt_instrument("benchmark", default_type="INDEX")
    start, end = _prompt_date_range()
    interval = _prompt_interval()

    s_price = _load_nubra_series(primary_req, start, end, interval)
    b_price = _load_nubra_series(benchmark_req, start, end, interval)

    aligned = pd.concat([s_price, b_price], axis=1, join="inner").dropna()
    if aligned.empty:
        raise ValueError("No overlapping dates between symbol and benchmark.")

    s_ret, s_eq = _to_returns_equity(aligned.iloc[:, 0].rename(primary_req.symbol))
    b_ret, b_eq = _to_returns_equity(aligned.iloc[:, 1].rename(benchmark_req.symbol))

    _line()
    print(f"Comparison: {primary_req.symbol} vs {benchmark_req.symbol}")
    ns.reports.metrics(returns=s_ret, benchmark=b_ret, display=True)

    save = _prompt("Save comparison plots as PNG? (y/n)", "y").lower()
    if save == "y":
        out_dir = _ensure_output_dir()
        ns.plots.equity_curve(
            s_eq,
            benchmark=b_eq,
            title=f"{primary_req.symbol} vs {benchmark_req.symbol} Equity Curve",
            show=False,
            savefig={
                "fname": str(
                    out_dir / f"{primary_req.symbol}_vs_{benchmark_req.symbol}_equity.png"
                )
            },
        )
        ns.plots.drawdown(
            equity=s_eq,
            title=f"{primary_req.symbol} Drawdown",
            show=False,
            savefig={"fname": str(out_dir / f"{primary_req.symbol}_drawdown.png")},
        )
        ns.plots.drawdown(
            equity=b_eq,
            title=f"{benchmark_req.symbol} Drawdown",
            show=False,
            savefig={"fname": str(out_dir / f"{benchmark_req.symbol}_drawdown.png")},
        )
        print(f"Saved comparison plots in: {out_dir.resolve()}")


def run_html_report() -> None:
    _line()
    print("HTML Tearsheet (single symbol)")
    symbol_req = _prompt_instrument("report", default_type="STOCK")
    start, end = _prompt_date_range()
    interval = _prompt_interval()
    prices = _load_nubra_series(symbol_req, start, end, interval)
    returns, _ = _to_returns_equity(prices)

    out_dir = _ensure_output_dir()
    output_name = _prompt("Output HTML filename", f"{symbol_req.symbol.lower()}_report.html")
    output_path = out_dir / output_name

    generated = ns.reports.html(
        returns=returns,
        title=f"{symbol_req.symbol} Performance Tearsheet",
        output=str(output_path),
    )
    print(f"Generated report: {Path(generated).resolve()}")


def main() -> None:
    print("NubraStats Interactive Tester")
    while True:
        choice = _prompt_choice(
            "Choose an action",
            {
                "1": "Single symbol analysis",
                "2": "Compare symbol with benchmark instrument",
                "3": "Generate HTML report",
                "4": "Explain what library does and calculations",
                "5": "Exit",
            },
        )

        try:
            if choice == "1":
                run_single_symbol()
            elif choice == "2":
                run_compare_symbols()
            elif choice == "3":
                run_html_report()
            elif choice == "4":
                print_library_explainer()
            else:
                print("Exiting.")
                return
        except Exception as exc:
            print(f"Error: {exc}")

        _line()
        again = _prompt("Run another action? (y/n)", "y").lower()
        if again != "y":
            print("Exiting.")
            return


if __name__ == "__main__":
    main()
