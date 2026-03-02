from __future__ import annotations

import webbrowser
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from . import plots, reports, utils

NUBRA_INTERVALS = {"1s", "1m", "2m", "3m", "5m", "15m", "30m", "1h", "1d", "1w", "1mt"}
NUBRA_TYPES = {"STOCK", "INDEX", "OPT", "FUT"}


@dataclass(frozen=True)
class Instrument:
    symbol: str
    exchange: str = "NSE"
    instrument_type: str = "STOCK"


@dataclass(frozen=True)
class PortfolioPosition:
    symbol: str
    quantity: float
    exchange: str = "NSE"
    instrument_type: str = "STOCK"


def _price_scale_factor(price_scale: str) -> float:
    scale = str(price_scale).strip().lower()
    if scale in {"paise", "paisa", "ps"}:
        return 100.0
    if scale in {"rupee", "rupees", "inr", "raw"}:
        return 1.0
    raise ValueError("price_scale must be one of: paise, rupee/raw")


def to_utc_iso(value: str | pd.Timestamp) -> str:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    else:
        stamp = stamp.tz_convert("UTC")
    return stamp.isoformat().replace("+00:00", "Z")


def _normalize_bounds(
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    start_ts = pd.Timestamp(start).normalize()
    end_ts = pd.Timestamp(end).normalize() + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    if end_ts < start_ts:
        raise ValueError("end must be greater than or equal to start")
    return start_ts, end_ts


def build_historical_payload(
    *,
    symbol: str,
    exchange: str,
    instrument_type: str,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    interval: str = "1d",
    fields: list[str] | None = None,
) -> dict[str, Any]:
    interval_upper = str(interval)
    if interval_upper not in NUBRA_INTERVALS:
        raise ValueError(f"interval must be one of {sorted(NUBRA_INTERVALS)}")

    type_upper = str(instrument_type).upper()
    if type_upper not in NUBRA_TYPES:
        raise ValueError(f"instrument_type must be one of {sorted(NUBRA_TYPES)}")

    start_ts, end_ts = _normalize_bounds(start, end)
    req_fields = fields or ["close"]

    return {
        "exchange": str(exchange).upper(),
        "type": type_upper,
        "values": [str(symbol).upper()],
        "fields": req_fields,
        "startDate": to_utc_iso(start_ts),
        "endDate": to_utc_iso(end_ts),
        "interval": interval_upper,
        "intraDay": False,
        "realTime": False,
    }


def _get_field(value: Any, name: str) -> Any | None:
    if isinstance(value, Mapping):
        if name in value:
            return value[name]
        target = name.lower()
        for key, item in value.items():
            if str(key).lower() == target:
                return item
        return None
    direct = getattr(value, name, None)
    if direct is not None:
        return direct
    target = name.lower()
    for key in dir(value):
        if key.lower() == target:
            try:
                return getattr(value, key)
            except Exception:
                return None
    return None


def _iter_symbol_entries(symbol_map: Any) -> list[tuple[str, Any]]:
    if isinstance(symbol_map, Mapping):
        return [(str(k), v) for k, v in symbol_map.items()]

    items = getattr(symbol_map, "items", None)
    if callable(items):
        try:
            return [(str(k), v) for k, v in items()]
        except Exception:
            pass

    for method_name in ("model_dump", "dict"):
        method = getattr(symbol_map, method_name, None)
        if callable(method):
            try:
                dumped = method()
            except Exception:
                continue
            if isinstance(dumped, Mapping):
                return [(str(k), v) for k, v in dumped.items()]

    if hasattr(symbol_map, "__dict__"):
        return [
            (str(k), v)
            for k, v in vars(symbol_map).items()
            if not str(k).startswith("_")
        ]
    return []


def _symbol_matches(target: str, value: str) -> bool:
    raw = str(value).upper()
    if raw == target:
        return True
    for sep in (":", "/", "|"):
        if raw.endswith(f"{sep}{target}"):
            return True
    if raw.startswith(f"{target}-"):
        return True
    return False


def _iter_point_candidates(points: Any) -> list[Any]:
    if points is None:
        return []
    if isinstance(points, Mapping):
        return [points]
    if isinstance(points, (list, tuple)):
        return list(points)
    if isinstance(points, Iterable) and not isinstance(points, (str, bytes)):
        return list(points)
    return [points]


def _parse_ts_val(point: Any) -> tuple[Any | None, Any | None]:
    if isinstance(point, Mapping):
        ts = point.get("timestamp")
        if ts is None:
            ts = point.get("time") or point.get("ts") or point.get("date") or point.get("datetime")
        val = point.get("value")
        if val is None:
            val = point.get("close")
        if val is None:
            val = point.get("c")
        return ts, val

    if isinstance(point, (list, tuple)):
        values = list(point)
        if len(values) >= 5:
            return values[0], values[4]
        if len(values) >= 2:
            return values[0], values[1]
        return None, None

    ts = getattr(point, "timestamp", None)
    if ts is None:
        ts = getattr(point, "time", None) or getattr(point, "ts", None)
    val = getattr(point, "value", None)
    if val is None:
        val = getattr(point, "close", None)
    if val is None:
        val = getattr(point, "c", None)
    return ts, val


def _extract_rows_from_field_values(field_values: Any) -> list[tuple[pd.Timestamp, float]]:
    rows: list[tuple[pd.Timestamp, float]] = []
    sources = [
        "close",
        "charts",
        "chart",
        "candles",
        "ohlc",
        "values",
    ]
    for source in sources:
        points = _get_field(field_values, source)
        for point in _iter_point_candidates(points):
            raw_ts, raw_val = _parse_ts_val(point)
            if raw_ts is None or raw_val is None:
                continue
            rows.append((utils.to_timestamp(raw_ts), float(raw_val)))
    return rows


def close_series_from_historical_response(
    response: Any,
    symbol: str,
    *,
    price_scale: str = "paise",
) -> pd.Series:
    target = str(symbol).upper()
    rows: list[tuple[pd.Timestamp, float]] = []
    scale_factor = _price_scale_factor(price_scale)

    for data_block in getattr(response, "result", []) or []:
        for symbol_map in getattr(data_block, "values", []) or []:
            entries = _iter_symbol_entries(symbol_map)
            if not entries:
                continue
            matched = [(name, value) for name, value in entries if _symbol_matches(target, name)]
            selected = matched if matched else (entries if len(entries) == 1 else [])
            for _, field_values in selected:
                for ts, value in _extract_rows_from_field_values(field_values):
                    rows.append((ts, float(value) / scale_factor))

    if not rows:
        return pd.Series(dtype=float, name=target)

    df = pd.DataFrame(rows, columns=["timestamp", "close"]).dropna()
    df = df.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    series = pd.Series(
        pd.to_numeric(df["close"], errors="coerce").values,
        index=pd.to_datetime(df["timestamp"]),
        name=target,
    ).dropna()
    return series.sort_index()


def fetch_close_series(
    md_client: Any,
    *,
    symbol: str,
    exchange: str = "NSE",
    instrument_type: str = "STOCK",
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    interval: str = "1d",
    price_scale: str = "paise",
) -> pd.Series:
    payload = build_historical_payload(
        symbol=symbol,
        exchange=exchange,
        instrument_type=instrument_type,
        start=start,
        end=end,
        interval=interval,
        fields=["close"],
    )
    response = md_client.historical_data(payload)
    series = close_series_from_historical_response(
        response,
        symbol=symbol,
        price_scale=price_scale,
    )
    start_ts, end_ts = _normalize_bounds(start, end)

    if series.empty:
        message = getattr(response, "message", "No response message")
        raise ValueError(
            f"Unable to fetch price data for {str(symbol).upper()} "
            f"[{str(exchange).upper()}/{str(instrument_type).upper()}]. "
            f"The symbol may be invalid, unsupported, or unavailable in the selected environment/date range "
            f"(API message: {message})."
        )

    series = series[(series.index >= start_ts) & (series.index <= end_ts)]
    if series.empty:
        message = getattr(response, "message", "No response message")
        raise ValueError(
            f"No price data was available for {str(symbol).upper()} "
            f"[{str(exchange).upper()}/{str(instrument_type).upper()}] in the selected date range. "
            f"Check the symbol, market, interval, and dates "
            f"(API message: {message})."
        )
    return series


def _returns_from_prices(prices: pd.Series) -> tuple[pd.Series, pd.Series]:
    returns = utils.to_series(utils.to_returns(prices)).dropna()
    equity = utils.to_series(utils.to_equity(returns, start_balance=100000.0)).dropna()
    returns = returns[~returns.index.duplicated(keep="last")].sort_index()
    equity = equity[~equity.index.duplicated(keep="last")].sort_index()
    return returns, equity


def _normalize_positions(positions: Iterable[Any]) -> list[PortfolioPosition]:
    normalized: list[PortfolioPosition] = []
    seen: set[tuple[str, str, str]] = set()

    for raw in positions:
        if isinstance(raw, PortfolioPosition):
            pos = raw
        elif isinstance(raw, Mapping):
            pos = PortfolioPosition(
                symbol=str(raw.get("symbol", "")).strip().upper(),
                exchange=str(raw.get("exchange", "NSE")).strip().upper(),
                instrument_type=str(raw.get("instrument_type", "STOCK")).strip().upper(),
                quantity=float(raw.get("quantity", raw.get("qty", 0))),
            )
        else:
            pos = PortfolioPosition(
                symbol=str(getattr(raw, "symbol", "")).strip().upper(),
                exchange=str(getattr(raw, "exchange", "NSE")).strip().upper(),
                instrument_type=str(getattr(raw, "instrument_type", "STOCK")).strip().upper(),
                quantity=float(getattr(raw, "quantity", getattr(raw, "qty", 0))),
            )

        if not pos.symbol:
            raise ValueError("Each portfolio item must include a symbol")
        if pos.quantity <= 0:
            raise ValueError(f"Quantity must be > 0 for symbol {pos.symbol}")
        if pos.instrument_type not in NUBRA_TYPES:
            raise ValueError(f"instrument_type must be one of {sorted(NUBRA_TYPES)}")

        key = (pos.symbol, pos.exchange, pos.instrument_type)
        if key in seen:
            raise ValueError(
                f"Duplicate portfolio instrument not allowed: "
                f"{pos.symbol} [{pos.exchange}/{pos.instrument_type}]"
            )
        seen.add(key)
        normalized.append(pos)

    if not normalized:
        raise ValueError("Portfolio must contain at least one position")
    return normalized


def analyze_portfolio(
    md_client: Any,
    *,
    positions: Iterable[Any],
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    interval: str = "1d",
    price_scale: str = "paise",
    portfolio_name: str = "Portfolio",
    benchmark_symbol: str | None = None,
    benchmark_exchange: str = "NSE",
    benchmark_instrument_type: str = "INDEX",
    rf: float = 0.06,
    periods_per_year: int = 252,
    show_plots: bool = True,
    save_plots: bool = False,
    plots_dir: str | None = None,
    generate_html: bool = False,
    open_html: bool = False,
    html_output: str | None = None,
    html_mode: str = "basic",
    title: str | None = None,
    display_metrics: bool = True,
) -> dict[str, Any]:
    pos = _normalize_positions(positions)

    price_series: list[pd.Series] = []
    ordered_keys: list[str] = []
    qty_map: dict[str, float] = {}
    for item in pos:
        key = f"{item.symbol}|{item.exchange}|{item.instrument_type}"
        ordered_keys.append(key)
        qty_map[key] = float(item.quantity)
        try:
            series = fetch_close_series(
                md_client,
                symbol=item.symbol,
                exchange=item.exchange,
                instrument_type=item.instrument_type,
                start=start,
                end=end,
                interval=interval,
                price_scale=price_scale,
            )
        except Exception as exc:
            raise ValueError(
                f"Portfolio symbol failed: {item.symbol} [{item.exchange}/{item.instrument_type}]. {exc}"
            ) from exc
        price_series.append(series.rename(key))

    components = pd.concat(price_series, axis=1, join="inner").dropna()
    if components.empty:
        raise ValueError("No overlapping timestamps across portfolio symbols")

    first_prices = components.iloc[0]
    start_values = {
        col: float(first_prices[col]) * qty_map[col]
        for col in components.columns
    }
    total_start_value = sum(start_values.values())
    if total_start_value <= 0:
        raise ValueError("Portfolio start value is non-positive; check quantities/prices")

    weights = {
        col: start_values[col] / total_start_value
        for col in components.columns
    }

    portfolio_value = pd.Series(0.0, index=components.index, name="PORTFOLIO_VALUE")
    for col in components.columns:
        portfolio_value = portfolio_value + components[col] * qty_map[col]

    returns, equity = _returns_from_prices(portfolio_value.rename("PORTFOLIO"))

    benchmark_returns: pd.Series | None = None
    benchmark_equity: pd.Series | None = None
    benchmark_prices: pd.Series | None = None
    if benchmark_symbol:
        try:
            benchmark_prices = fetch_close_series(
                md_client,
                symbol=benchmark_symbol,
                exchange=benchmark_exchange,
                instrument_type=benchmark_instrument_type,
                start=start,
                end=end,
                interval=interval,
                price_scale=price_scale,
            )
        except Exception as exc:
            raise ValueError(
                f"Benchmark symbol failed: {str(benchmark_symbol).upper()} "
                f"[{str(benchmark_exchange).upper()}/{str(benchmark_instrument_type).upper()}]. {exc}"
            ) from exc
        aligned = pd.concat([portfolio_value, benchmark_prices], axis=1, join="inner").dropna()
        if aligned.empty:
            raise ValueError("No overlapping timestamps between portfolio and benchmark symbols")
        returns, equity = _returns_from_prices(aligned.iloc[:, 0].rename("PORTFOLIO"))
        benchmark_returns, benchmark_equity = _returns_from_prices(
            aligned.iloc[:, 1].rename(str(benchmark_symbol).upper())
        )

    name = portfolio_name.strip().upper()
    strategy_label = name or f"PORTFOLIO ({len(pos)})"
    benchmark_label = str(benchmark_symbol).upper() if benchmark_symbol else "Benchmark"
    scale_name = str(price_scale).strip().lower()
    if scale_name in {"paise", "paisa", "ps"}:
        plot_note = "Close prices from Nubra are converted from paise to rupees (value/100)."
    else:
        plot_note = "Close prices are used as provided (no paise conversion)."

    metrics_df = reports.metrics(
        returns=returns,
        equity=equity,
        benchmark=benchmark_returns,
        strategy_label=strategy_label,
        benchmark_label=benchmark_label,
        rf=rf,
        periods_per_year=periods_per_year,
        display=display_metrics,
    )

    plot_paths: dict[str, str] = {}
    if show_plots or save_plots:
        out_dir = Path(plots_dir or "nubrastats-plots")
        if save_plots:
            out_dir.mkdir(parents=True, exist_ok=True)

        def _save_cfg(name: str) -> dict[str, Any] | None:
            if not save_plots:
                return None
            file_path = out_dir / name
            plot_paths[name] = str(file_path.resolve())
            return {"fname": str(file_path)}

        if benchmark_symbol:
            equity_title = f"{strategy_label} vs {benchmark_label} Equity Curve"
        else:
            equity_title = f"{strategy_label} Equity Curve"
        plots.equity_curve(
            equity,
            benchmark=benchmark_equity,
            title=equity_title,
            strategy_label=strategy_label,
            benchmark_label=benchmark_label if benchmark_symbol else None,
            subtitle_note=plot_note,
            show=show_plots,
            savefig=_save_cfg("equity_curve.png"),
        )
        plots.drawdown(
            equity=equity,
            title=f"{strategy_label} Drawdown",
            subtitle_note=plot_note,
            show=show_plots,
            savefig=_save_cfg("drawdown.png"),
        )
        plots.monthly_heatmap(
            returns,
            title=f"{strategy_label} Monthly Returns",
            subtitle_note=plot_note,
            show=show_plots,
            savefig=_save_cfg("monthly_heatmap.png"),
        )
        plots.rolling_sharpe(
            returns,
            rf=rf,
            periods_per_year=periods_per_year,
            title=f"{strategy_label} Rolling Sharpe",
            subtitle_note=plot_note,
            show=show_plots,
            savefig=_save_cfg("rolling_sharpe.png"),
        )

    html_path: str | None = None
    html_opened = False
    if generate_html:
        if title:
            html_title = title
        elif benchmark_symbol:
            html_title = f"{strategy_label} vs {benchmark_label} Nubra Report"
        else:
            html_title = f"{strategy_label} Nubra Report"
        html_path = reports.html(
            returns=returns,
            equity=equity,
            benchmark=benchmark_returns,
            strategy_label=strategy_label,
            benchmark_label=benchmark_label,
            rf=rf,
            periods_per_year=periods_per_year,
            title=html_title,
            output=html_output,
            mode=html_mode,
        )
        if open_html and html_path:
            html_uri = Path(html_path).resolve().as_uri()
            html_opened = bool(webbrowser.open(html_uri))

    portfolio_items = [
        {
            "symbol": item.symbol,
            "exchange": item.exchange,
            "instrument_type": item.instrument_type,
            "quantity": float(item.quantity),
        }
        for item in pos
    ]
    component_prices = components.copy()
    weight_series = pd.Series(weights, name="start_weight").sort_values(ascending=False)

    return {
        "prices": portfolio_value.rename(strategy_label),
        "returns": returns,
        "equity": equity,
        "benchmark_prices": benchmark_prices,
        "benchmark_returns": benchmark_returns,
        "benchmark_equity": benchmark_equity,
        "price_scale": price_scale,
        "metrics": metrics_df,
        "plot_paths": plot_paths,
        "html_path": html_path,
        "html_opened": html_opened,
        "html_mode": html_mode,
        "strategy_label": strategy_label,
        "portfolio_items": portfolio_items,
        "portfolio_weights": weight_series,
        "component_prices": component_prices,
    }


def analyze_symbol(
    md_client: Any,
    *,
    symbol: str,
    exchange: str = "NSE",
    instrument_type: str = "STOCK",
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    interval: str = "1d",
    price_scale: str = "paise",
    benchmark_symbol: str | None = None,
    benchmark_exchange: str = "NSE",
    benchmark_instrument_type: str = "INDEX",
    rf: float = 0.06,
    periods_per_year: int = 252,
    show_plots: bool = True,
    save_plots: bool = False,
    plots_dir: str | None = None,
    generate_html: bool = False,
    open_html: bool = False,
    html_output: str | None = None,
    html_mode: str = "basic",
    title: str | None = None,
    display_metrics: bool = True,
) -> dict[str, Any]:
    """
    Minimal end-user pipeline:
    fetch prices -> compute returns/equity -> metrics -> optional plots/html.
    """
    try:
        primary_prices = fetch_close_series(
            md_client,
            symbol=symbol,
            exchange=exchange,
            instrument_type=instrument_type,
            start=start,
            end=end,
            interval=interval,
            price_scale=price_scale,
        )
    except Exception as exc:
        raise ValueError(
            f"Primary symbol failed: {str(symbol).upper()} "
            f"[{str(exchange).upper()}/{str(instrument_type).upper()}]. {exc}"
        ) from exc
    returns, equity = _returns_from_prices(primary_prices)

    benchmark_returns: pd.Series | None = None
    benchmark_equity: pd.Series | None = None
    benchmark_prices: pd.Series | None = None

    if benchmark_symbol:
        try:
            benchmark_prices = fetch_close_series(
                md_client,
                symbol=benchmark_symbol,
                exchange=benchmark_exchange,
                instrument_type=benchmark_instrument_type,
                start=start,
                end=end,
                interval=interval,
                price_scale=price_scale,
            )
        except Exception as exc:
            raise ValueError(
                f"Benchmark symbol failed: {str(benchmark_symbol).upper()} "
                f"[{str(benchmark_exchange).upper()}/{str(benchmark_instrument_type).upper()}]. {exc}"
            ) from exc
        aligned = pd.concat([primary_prices, benchmark_prices], axis=1, join="inner").dropna()
        if aligned.empty:
            raise ValueError("No overlapping timestamps between primary and benchmark symbols")
        returns, equity = _returns_from_prices(aligned.iloc[:, 0].rename(str(symbol).upper()))
        benchmark_returns, benchmark_equity = _returns_from_prices(
            aligned.iloc[:, 1].rename(str(benchmark_symbol).upper())
        )

    strategy_label = str(symbol).upper()
    benchmark_label = str(benchmark_symbol).upper() if benchmark_symbol else "Benchmark"
    scale_name = str(price_scale).strip().lower()
    if scale_name in {"paise", "paisa", "ps"}:
        plot_note = "Close prices from Nubra are converted from paise to rupees (value/100)."
    else:
        plot_note = "Close prices are used as provided (no paise conversion)."

    metrics_df = reports.metrics(
        returns=returns,
        equity=equity,
        benchmark=benchmark_returns,
        strategy_label=strategy_label,
        benchmark_label=benchmark_label,
        rf=rf,
        periods_per_year=periods_per_year,
        display=display_metrics,
    )

    plot_paths: dict[str, str] = {}
    if show_plots or save_plots:
        out_dir = Path(plots_dir or "nubrastats-plots")
        if save_plots:
            out_dir.mkdir(parents=True, exist_ok=True)

        def _save_cfg(name: str) -> dict[str, Any] | None:
            if not save_plots:
                return None
            file_path = out_dir / name
            plot_paths[name] = str(file_path.resolve())
            return {"fname": str(file_path)}

        base_name = str(symbol).upper()
        if benchmark_symbol:
            equity_title = f"{base_name} vs {benchmark_label} Equity Curve"
        else:
            equity_title = f"{base_name} Equity Curve"
        plots.equity_curve(
            equity,
            benchmark=benchmark_equity,
            title=equity_title,
            strategy_label=strategy_label,
            benchmark_label=benchmark_label if benchmark_symbol else None,
            subtitle_note=plot_note,
            show=show_plots,
            savefig=_save_cfg("equity_curve.png"),
        )
        plots.drawdown(
            equity=equity,
            title=f"{base_name} Drawdown",
            subtitle_note=plot_note,
            show=show_plots,
            savefig=_save_cfg("drawdown.png"),
        )
        plots.monthly_heatmap(
            returns,
            title=f"{base_name} Monthly Returns",
            subtitle_note=plot_note,
            show=show_plots,
            savefig=_save_cfg("monthly_heatmap.png"),
        )
        plots.rolling_sharpe(
            returns,
            rf=rf,
            periods_per_year=periods_per_year,
            title=f"{base_name} Rolling Sharpe",
            subtitle_note=plot_note,
            show=show_plots,
            savefig=_save_cfg("rolling_sharpe.png"),
        )

    html_path: str | None = None
    html_opened = False
    if generate_html:
        if title:
            html_title = title
        elif benchmark_symbol:
            html_title = f"{strategy_label} vs {benchmark_label} Nubra Report"
        else:
            html_title = f"{strategy_label} Nubra Report"
        html_path = reports.html(
            returns=returns,
            equity=equity,
            benchmark=benchmark_returns,
            strategy_label=strategy_label,
            benchmark_label=benchmark_label,
            rf=rf,
            periods_per_year=periods_per_year,
            title=html_title,
            output=html_output,
            mode=html_mode,
        )
        if open_html and html_path:
            html_uri = Path(html_path).resolve().as_uri()
            html_opened = bool(webbrowser.open(html_uri))

    return {
        "prices": primary_prices,
        "returns": returns,
        "equity": equity,
        "benchmark_prices": benchmark_prices,
        "benchmark_returns": benchmark_returns,
        "benchmark_equity": benchmark_equity,
        "price_scale": price_scale,
        "metrics": metrics_df,
        "plot_paths": plot_paths,
        "html_path": html_path,
        "html_opened": html_opened,
        "html_mode": html_mode,
        "strategy_label": strategy_label,
    }
