from __future__ import annotations

import pandas as pd
import pytest

from nubrastats import nubra


class _Point:
    def __init__(self, timestamp: int, value: float) -> None:
        self.timestamp = timestamp
        self.value = value


class _FieldValues:
    def __init__(self, close: list[_Point]) -> None:
        self.close = close


class _DataBlock:
    def __init__(self, values: list[dict[str, _FieldValues]]) -> None:
        self.values = values


class _Response:
    def __init__(self, result, message: str = "charts") -> None:
        self.result = result
        self.message = message


class _FakeMDClient:
    def __init__(self, response: _Response) -> None:
        self._response = response
        self.last_payload = None

    def historical_data(self, payload):
        self.last_payload = payload
        return self._response


class _QueueMDClient:
    def __init__(self, responses: list[_Response]) -> None:
        self._responses = responses
        self.payloads: list[dict] = []

    def historical_data(self, payload):
        self.payloads.append(payload)
        if not self._responses:
            return _Response(result=[], message="empty queue")
        return self._responses.pop(0)


def _ts_ns(value: str) -> int:
    return int(pd.Timestamp(value).tz_localize("UTC").value)


def test_build_historical_payload() -> None:
    payload = nubra.build_historical_payload(
        symbol="RELIANCE",
        exchange="NSE",
        instrument_type="STOCK",
        start="2025-01-01",
        end="2025-01-10",
        interval="1d",
    )
    assert payload["exchange"] == "NSE"
    assert payload["type"] == "STOCK"
    assert payload["values"] == ["RELIANCE"]
    assert payload["fields"] == ["close"]
    assert payload["interval"] == "1d"


def test_close_series_from_historical_response_sorted() -> None:
    t1 = _ts_ns("2025-01-01 10:00:00")
    t2 = _ts_ns("2025-01-02 10:00:00")
    response = _Response(
        result=[
            _DataBlock(
                values=[
                    {
                        "RELIANCE": _FieldValues(
                            close=[
                                _Point(t2, 10100.0),
                                _Point(t1, 10000.0),
                            ]
                        )
                    }
                ]
            )
        ]
    )

    series = nubra.close_series_from_historical_response(response, symbol="RELIANCE")
    assert list(series.values) == [100.0, 101.0]
    assert series.name == "RELIANCE"


def test_close_series_from_historical_response_dict_close_points() -> None:
    t1 = _ts_ns("2025-01-01 10:00:00")
    t2 = _ts_ns("2025-01-02 10:00:00")
    response = _Response(
        result=[
            _DataBlock(
                values=[
                    {
                        "RELIANCE": {
                            "close": [
                                {"timestamp": t2, "value": 10100.0},
                                {"timestamp": t1, "value": 10000.0},
                            ]
                        }
                    }
                ]
            )
        ]
    )

    series = nubra.close_series_from_historical_response(response, symbol="RELIANCE")
    assert list(series.values) == [100.0, 101.0]


def test_close_series_from_historical_response_charts_ohlc_points() -> None:
    t1 = _ts_ns("2025-01-01 10:00:00")
    t2 = _ts_ns("2025-01-02 10:00:00")
    response = _Response(
        result=[
            _DataBlock(
                values=[
                    {
                        "NSE:HAL": {
                            "charts": [
                                [t1, 9900.0, 10200.0, 9800.0, 10000.0, 1000],
                                [t2, 10000.0, 10300.0, 9900.0, 10100.0, 1200],
                            ]
                        }
                    }
                ]
            )
        ]
    )

    series = nubra.close_series_from_historical_response(response, symbol="HAL")
    assert list(series.values) == [100.0, 101.0]


def test_fetch_close_series_uses_payload_and_filters_dates() -> None:
    t1 = _ts_ns("2025-01-01 10:00:00")
    t2 = _ts_ns("2025-01-03 10:00:00")
    response = _Response(
        result=[
            _DataBlock(
                values=[
                    {
                        "RELIANCE": _FieldValues(
                            close=[
                                _Point(t1, 10000.0),
                                _Point(t2, 10200.0),
                            ]
                        )
                    }
                ]
            )
        ]
    )
    md = _FakeMDClient(response)

    series = nubra.fetch_close_series(
        md,
        symbol="RELIANCE",
        exchange="NSE",
        instrument_type="STOCK",
        start="2025-01-01",
        end="2025-01-02",
        interval="1d",
    )

    assert list(series.values) == [100.0]
    assert md.last_payload is not None
    assert md.last_payload["fields"] == ["close"]
    assert md.last_payload["values"] == ["RELIANCE"]


def test_fetch_close_series_raises_when_no_data() -> None:
    response = _Response(result=[], message="no data")
    md = _FakeMDClient(response)
    with pytest.raises(ValueError):
        nubra.fetch_close_series(
            md,
            symbol="RELIANCE",
            exchange="NSE",
            instrument_type="STOCK",
            start="2025-01-01",
            end="2025-01-02",
            interval="1d",
        )


def test_analyze_symbol_minimal_pipeline() -> None:
    t1 = _ts_ns("2025-01-01 10:00:00")
    t2 = _ts_ns("2025-01-02 10:00:00")
    response = _Response(
        result=[
            _DataBlock(
                values=[
                    {
                        "RELIANCE": _FieldValues(
                            close=[
                                _Point(t1, 10000.0),
                                _Point(t2, 10100.0),
                            ]
                        )
                    }
                ]
            )
        ]
    )
    md = _QueueMDClient([response])

    result = nubra.analyze_symbol(
        md,
        symbol="RELIANCE",
        exchange="NSE",
        instrument_type="STOCK",
        start="2025-01-01",
        end="2025-01-02",
        interval="1d",
        show_plots=False,
        save_plots=False,
        generate_html=False,
        display_metrics=False,
    )

    assert not result["returns"].empty
    assert not result["equity"].empty
    assert result["metrics"].shape[0] > 0
    assert result["plot_paths"] == {}
    assert result["html_path"] is None


def test_analyze_symbol_with_benchmark_and_optional_saves(monkeypatch) -> None:
    t1 = _ts_ns("2025-01-01 10:00:00")
    t2 = _ts_ns("2025-01-02 10:00:00")
    primary = _Response(
        result=[
            _DataBlock(
                values=[
                    {
                        "RELIANCE": _FieldValues(
                            close=[
                                _Point(t1, 10000.0),
                                _Point(t2, 10100.0),
                            ]
                        )
                    }
                ]
            )
        ]
    )
    benchmark = _Response(
        result=[
            _DataBlock(
                values=[
                    {
                        "NIFTY": _FieldValues(
                            close=[
                                _Point(t1, 20000.0),
                                _Point(t2, 20100.0),
                            ]
                        )
                    }
                ]
            )
        ]
    )
    md = _QueueMDClient([primary, benchmark])

    def _fake_plot(*args, **kwargs):
        return None

    monkeypatch.setattr(nubra.plots, "equity_curve", _fake_plot)
    monkeypatch.setattr(nubra.plots, "drawdown", _fake_plot)
    monkeypatch.setattr(nubra.plots, "monthly_heatmap", _fake_plot)
    monkeypatch.setattr(nubra.plots, "rolling_sharpe", _fake_plot)
    monkeypatch.setattr(nubra.reports, "html", lambda **kwargs: "out.html")
    opened_urls: list[str] = []
    monkeypatch.setattr(
        nubra.webbrowser,
        "open",
        lambda url: opened_urls.append(url) or True,
    )

    result = nubra.analyze_symbol(
        md,
        symbol="RELIANCE",
        exchange="NSE",
        instrument_type="STOCK",
        start="2025-01-01",
        end="2025-01-02",
        interval="1d",
        benchmark_symbol="NIFTY",
        benchmark_exchange="NSE",
        benchmark_instrument_type="INDEX",
        show_plots=False,
        save_plots=True,
        plots_dir="tmp_plots",
        generate_html=True,
        open_html=True,
        html_output="out.html",
        display_metrics=False,
    )

    assert result["benchmark_returns"] is not None
    assert result["benchmark_equity"] is not None
    assert "RELIANCE" in result["metrics"].columns
    assert "NIFTY" in result["metrics"].columns
    assert set(result["plot_paths"].keys()) == {
        "equity_curve.png",
        "drawdown.png",
        "monthly_heatmap.png",
        "rolling_sharpe.png",
    }
    assert result["html_path"] == "out.html"
    assert result["html_opened"] is True
    assert len(opened_urls) == 1


def test_analyze_portfolio_minimal_pipeline() -> None:
    t1 = _ts_ns("2025-01-01 10:00:00")
    t2 = _ts_ns("2025-01-02 10:00:00")
    rel = _Response(
        result=[
            _DataBlock(
                values=[
                    {
                        "RELIANCE": _FieldValues(
                            close=[
                                _Point(t1, 10000.0),
                                _Point(t2, 10100.0),
                            ]
                        )
                    }
                ]
            )
        ]
    )
    tcs = _Response(
        result=[
            _DataBlock(
                values=[
                    {
                        "TCS": _FieldValues(
                            close=[
                                _Point(t1, 20000.0),
                                _Point(t2, 20200.0),
                            ]
                        )
                    }
                ]
            )
        ]
    )
    md = _QueueMDClient([rel, tcs])

    result = nubra.analyze_portfolio(
        md,
        positions=[
            {"symbol": "RELIANCE", "exchange": "NSE", "instrument_type": "STOCK", "quantity": 10},
            {"symbol": "TCS", "exchange": "NSE", "instrument_type": "STOCK", "quantity": 5},
        ],
        portfolio_name="Core",
        start="2025-01-01",
        end="2025-01-02",
        interval="1d",
        show_plots=False,
        save_plots=False,
        generate_html=False,
        display_metrics=False,
    )

    assert not result["returns"].empty
    assert not result["equity"].empty
    assert result["strategy_label"] == "CORE"
    assert "CORE" in result["metrics"].columns
    assert abs(float(result["portfolio_weights"].sum()) - 1.0) < 1e-9
    assert result["component_prices"].shape[1] == 2


def test_analyze_portfolio_rejects_duplicates() -> None:
    md = _QueueMDClient([])
    with pytest.raises(ValueError):
        nubra.analyze_portfolio(
            md,
            positions=[
                {
                    "symbol": "RELIANCE",
                    "exchange": "NSE",
                    "instrument_type": "STOCK",
                    "quantity": 10,
                },
                {
                    "symbol": "RELIANCE",
                    "exchange": "NSE",
                    "instrument_type": "STOCK",
                    "quantity": 5,
                },
            ],
            start="2025-01-01",
            end="2025-01-02",
            interval="1d",
            show_plots=False,
            save_plots=False,
            generate_html=False,
            display_metrics=False,
        )
