from __future__ import annotations

import sys
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

import nubrastats as ns

# ============================================================================
# USER PLACEHOLDERS (EDIT THESE VALUES)
# ============================================================================

# Nubra session
NUBRA_ENV = "UAT"  # UAT | PROD | DEV | STAGING
USE_ENV_CREDS = True  # True -> SDK reads credentials from .env
USE_TOTP_LOGIN = False

# Data request
START_DATE = "2025-01-01"  # YYYY-MM-DD
END_DATE = "2025-12-31"  # YYYY-MM-DD
INTERVAL = "1d"  # 1s,1m,2m,3m,5m,15m,30m,1h,1d,1w,1mt

# Primary instrument
PRIMARY_SYMBOL = "RELIANCE"
PRIMARY_EXCHANGE = "NSE"
PRIMARY_TYPE = "STOCK"  # STOCK | INDEX | OPT | FUT

# Optional benchmark comparison
ENABLE_BENCHMARK = True
BENCHMARK_SYMBOL = "NIFTY"
BENCHMARK_EXCHANGE = "NSE"
BENCHMARK_TYPE = "INDEX"  # STOCK | INDEX | OPT | FUT

# Output
OUTPUT_DIR = "test_outputs_static"
REPORT_NAME = "nubra_static_test_report.html"
SHOW_PLOTS = True  # pop up plots while running
SAVE_PNG = False  # optional: save plots as PNG
GENERATE_HTML = True  # optional: generate HTML report
OPEN_HTML_REPORT = True  # optional: open generated HTML in browser

# Validation thresholds
MIN_CANDLES_REQUIRED = 20
MAX_ALLOWED_NAN_RATIO = 0.05  # 5%


ALLOWED_INTERVALS = {"1s", "1m", "2m", "3m", "5m", "15m", "30m", "1h", "1d", "1w", "1mt"}
ALLOWED_TYPES = {"STOCK", "INDEX", "OPT", "FUT"}


@dataclass(frozen=True)
class Instrument:
    symbol: str
    exchange: str
    instrument_type: str


def _line() -> None:
    print("-" * 80)


def _to_utc_iso(ts: pd.Timestamp) -> str:
    stamp = pd.Timestamp(ts)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    else:
        stamp = stamp.tz_convert("UTC")
    return stamp.isoformat().replace("+00:00", "Z")


def _validate_config() -> None:
    if INTERVAL not in ALLOWED_INTERVALS:
        raise ValueError(f"INTERVAL must be one of {sorted(ALLOWED_INTERVALS)}")
    if PRIMARY_TYPE not in ALLOWED_TYPES:
        raise ValueError(f"PRIMARY_TYPE must be one of {sorted(ALLOWED_TYPES)}")
    if ENABLE_BENCHMARK and BENCHMARK_TYPE not in ALLOWED_TYPES:
        raise ValueError(f"BENCHMARK_TYPE must be one of {sorted(ALLOWED_TYPES)}")

    start = pd.to_datetime(START_DATE)
    end = pd.to_datetime(END_DATE)
    if end < start:
        raise ValueError("END_DATE must be >= START_DATE")


def _build_nubra_market_data_client() -> Any:
    from nubra_python_sdk.marketdata.market_data import MarketData
    from nubra_python_sdk.start_sdk import InitNubraSdk, NubraEnv

    env_name = NUBRA_ENV.strip().upper()
    env_map = {
        "UAT": NubraEnv.UAT,
        "PROD": NubraEnv.PROD,
        "DEV": NubraEnv.DEV,
        "STAGING": NubraEnv.STAGING,
    }
    if env_name not in env_map:
        raise ValueError(f"NUBRA_ENV must be one of {sorted(env_map.keys())}")

    nubra = InitNubraSdk(
        env=env_map[env_name],
        totp_login=USE_TOTP_LOGIN,
        env_creds=USE_ENV_CREDS,
    )
    return MarketData(nubra)


def _fetch_close_series(
    md_client: Any,
    request: Instrument,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.Series:
    payload = {
        "exchange": request.exchange,
        "type": request.instrument_type,
        "values": [request.symbol],
        "fields": ["close"],
        "startDate": _to_utc_iso(start),
        "endDate": _to_utc_iso(end),
        "interval": INTERVAL,
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
                if str(symbol_name).upper() != request.symbol.upper():
                    continue
                close_points = getattr(field_values, "close", None) or []
                for point in close_points:
                    ts = getattr(point, "timestamp", None)
                    val = getattr(point, "value", None)
                    if ts is None or val is None:
                        continue
                    rows.append((ns.utils.to_timestamp(ts), float(val)))

    if not rows:
        message = getattr(result, "message", "No response message")
        raise ValueError(
            f"No close data for {request.symbol} "
            f"[{request.exchange}/{request.instrument_type}] ({message})"
        )

    df = pd.DataFrame(rows, columns=["timestamp", "close"]).dropna()
    df = df.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    series = pd.Series(
        pd.to_numeric(df["close"], errors="coerce").values,
        index=pd.to_datetime(df["timestamp"]),
        name=request.symbol.upper(),
    ).dropna()

    series = series[(series.index >= start) & (series.index <= end)]
    if series.empty:
        raise ValueError(f"No rows after date filter for {request.symbol}")
    return series.sort_index()


def _to_returns_equity(prices: pd.Series) -> tuple[pd.Series, pd.Series]:
    returns = ns.utils.to_series(ns.utils.to_returns(prices)).dropna()
    equity = ns.utils.to_series(ns.utils.to_equity(returns, start_balance=100000.0)).dropna()
    returns = returns[~returns.index.duplicated(keep="last")].sort_index()
    equity = equity[~equity.index.duplicated(keep="last")].sort_index()
    return returns, equity


def _print_series_summary(label: str, s: pd.Series) -> None:
    _line()
    print(f"{label} summary")
    print(f"Rows: {len(s)}")
    print(f"Start: {s.index.min()} -> {float(s.iloc[0]):.4f}")
    print(f"End  : {s.index.max()} -> {float(s.iloc[-1]):.4f}")
    print(f"NaN ratio: {float(s.isna().mean()):.4%}")


def _save_outputs(
    primary_symbol: str,
    primary_returns: pd.Series,
    primary_equity: pd.Series,
    benchmark_returns: pd.Series | None,
    benchmark_equity: pd.Series | None,
    out_dir: Path,
) -> tuple[dict[str, str], Path | None]:
    plot_paths: dict[str, str] = {}
    report_path: Path | None = None

    if SAVE_PNG or GENERATE_HTML:
        out_dir.mkdir(parents=True, exist_ok=True)

    def _save_cfg(name: str) -> dict[str, str] | None:
        if not SAVE_PNG:
            return None
        file_path = out_dir / name
        plot_paths[name] = str(file_path.resolve())
        return {"fname": str(file_path)}

    ns.plots.equity_curve(
        primary_equity,
        benchmark=benchmark_equity,
        title=f"{primary_symbol} Equity Curve",
        show=SHOW_PLOTS,
        savefig=_save_cfg("equity_curve.png"),
    )
    ns.plots.drawdown(
        equity=primary_equity,
        title=f"{primary_symbol} Drawdown",
        show=SHOW_PLOTS,
        savefig=_save_cfg("drawdown.png"),
    )
    ns.plots.monthly_heatmap(
        primary_returns,
        title=f"{primary_symbol} Monthly Returns",
        show=SHOW_PLOTS,
        savefig=_save_cfg("monthly_heatmap.png"),
    )
    ns.plots.rolling_sharpe(
        primary_returns,
        title=f"{primary_symbol} Rolling Sharpe",
        show=SHOW_PLOTS,
        savefig=_save_cfg("rolling_sharpe.png"),
    )

    if GENERATE_HTML:
        report_path = out_dir / REPORT_NAME
        ns.reports.html(
            returns=primary_returns,
            benchmark=benchmark_returns,
            title=f"{primary_symbol} Static Test Report",
            output=str(report_path),
        )
    return plot_paths, report_path


def _run_checks(
    primary_prices: pd.Series,
    primary_returns: pd.Series,
    report_path: Path | None,
    benchmark_prices: pd.Series | None = None,
) -> bool:
    checks: list[tuple[str, bool, str]] = []

    checks.append(
        (
            "Primary candles",
            len(primary_prices) >= MIN_CANDLES_REQUIRED,
            f"found={len(primary_prices)}, required>={MIN_CANDLES_REQUIRED}",
        )
    )
    checks.append(
        (
            "Primary NaN ratio",
            float(primary_prices.isna().mean()) <= MAX_ALLOWED_NAN_RATIO,
            f"nan_ratio={float(primary_prices.isna().mean()):.4%}, "
            f"allowed<={MAX_ALLOWED_NAN_RATIO:.2%}",
        )
    )
    checks.append(
        (
            "Primary returns non-empty",
            not primary_returns.empty,
            f"return_rows={len(primary_returns)}",
        )
    )
    if report_path is not None:
        checks.append(
            (
                "HTML report generated",
                report_path.exists(),
                str(report_path),
            )
        )
    if benchmark_prices is not None:
        checks.append(
            (
                "Benchmark candles",
                len(benchmark_prices) >= MIN_CANDLES_REQUIRED,
                f"found={len(benchmark_prices)}, required>={MIN_CANDLES_REQUIRED}",
            )
        )

    _line()
    print("Validation checks")
    failed = False
    for name, ok, details in checks:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}: {details}")
        if not ok:
            failed = True
    return not failed


def main() -> None:
    _validate_config()

    start = pd.to_datetime(START_DATE).normalize()
    end = pd.to_datetime(END_DATE).normalize() + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)

    primary = Instrument(PRIMARY_SYMBOL.upper(), PRIMARY_EXCHANGE.upper(), PRIMARY_TYPE.upper())
    benchmark = Instrument(
        BENCHMARK_SYMBOL.upper(),
        BENCHMARK_EXCHANGE.upper(),
        BENCHMARK_TYPE.upper(),
    )

    _line()
    print("Nubra Static Test Runner")
    print(f"Env={NUBRA_ENV.upper()} | interval={INTERVAL} | range={START_DATE} -> {END_DATE}")
    print(f"Primary={primary.symbol} [{primary.exchange}/{primary.instrument_type}]")
    if ENABLE_BENCHMARK:
        print(f"Benchmark={benchmark.symbol} [{benchmark.exchange}/{benchmark.instrument_type}]")

    md_client = _build_nubra_market_data_client()

    primary_prices = _fetch_close_series(md_client, primary, start, end)
    _print_series_summary("Primary prices", primary_prices)
    primary_returns, primary_equity = _to_returns_equity(primary_prices)

    benchmark_prices: pd.Series | None = None
    benchmark_returns: pd.Series | None = None
    benchmark_equity: pd.Series | None = None

    if ENABLE_BENCHMARK:
        benchmark_prices = _fetch_close_series(md_client, benchmark, start, end)
        _print_series_summary("Benchmark prices", benchmark_prices)
        aligned = pd.concat([primary_prices, benchmark_prices], axis=1, join="inner").dropna()
        if aligned.empty:
            raise ValueError("No overlapping timestamps between primary and benchmark")
        primary_prices = aligned.iloc[:, 0].rename(primary.symbol)
        benchmark_prices = aligned.iloc[:, 1].rename(benchmark.symbol)
        primary_returns, primary_equity = _to_returns_equity(primary_prices)
        benchmark_returns, benchmark_equity = _to_returns_equity(benchmark_prices)

    _line()
    print("Metrics")
    ns.reports.metrics(
        returns=primary_returns,
        benchmark=benchmark_returns,
        display=True,
    )

    output_dir = Path(OUTPUT_DIR)
    plot_paths, report_path = _save_outputs(
        primary_symbol=primary.symbol,
        primary_returns=primary_returns,
        primary_equity=primary_equity,
        benchmark_returns=benchmark_returns,
        benchmark_equity=benchmark_equity,
        out_dir=output_dir,
    )
    _line()
    if SAVE_PNG or GENERATE_HTML:
        print(f"Output folder: {output_dir.resolve()}")
    if report_path is not None:
        print(f"Report file : {report_path.resolve()}")
        if OPEN_HTML_REPORT:
            webbrowser.open(report_path.resolve().as_uri())
            print("Opened report in browser.")
    if plot_paths:
        print("Plot files:")
        for _, path in plot_paths.items():
            print(path)

    all_ok = _run_checks(
        primary_prices=primary_prices,
        primary_returns=primary_returns,
        report_path=report_path,
        benchmark_prices=benchmark_prices if ENABLE_BENCHMARK else None,
    )
    if not all_ok:
        sys.exit(1)

    _line()
    print("All checks passed.")


if __name__ == "__main__":
    main()
