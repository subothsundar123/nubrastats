from pathlib import Path

import pandas as pd

from nubrastats import reports


def test_html_report_generation(tmp_path: Path):
    returns = pd.Series(
        [0.01, -0.005, 0.002, 0.004, -0.001, 0.003],
        index=pd.date_range("2026-01-01", periods=6, freq="D"),
    )
    output = tmp_path / "report.html"
    path = reports.html(returns=returns, title="Unit Test Report", output=str(output))
    assert Path(path).exists()
    content = Path(path).read_text(encoding="utf-8")
    assert "Unit Test Report" in content
    assert "Metrics" in content


def test_metrics_and_html_include_symbol_labels(tmp_path: Path):
    returns = pd.Series(
        [0.01, -0.005, 0.002, 0.004, -0.001, 0.003],
        index=pd.date_range("2026-01-01", periods=6, freq="D"),
    )
    benchmark = returns * 0.5

    mdf = reports.metrics(
        returns=returns,
        benchmark=benchmark,
        strategy_label="HAL",
        benchmark_label="NIFTY",
        display=False,
    )
    assert "HAL" in mdf.columns
    assert "NIFTY" in mdf.columns

    output = tmp_path / "report_labels.html"
    path = reports.html(
        returns=returns,
        benchmark=benchmark,
        strategy_label="HAL",
        benchmark_label="NIFTY",
        title="HAL vs NIFTY",
        output=str(output),
    )
    content = Path(path).read_text(encoding="utf-8")
    assert "Analyzed: HAL" in content
    assert "Compared with: NIFTY" in content


def test_detailed_html_report_generation(tmp_path: Path):
    returns = pd.Series(
        [0.01, -0.005, 0.002, 0.004, -0.001, 0.003, 0.006, -0.002],
        index=pd.date_range("2026-01-01", periods=8, freq="D"),
    )
    benchmark = returns * 0.6

    output = tmp_path / "detailed_report.html"
    path = reports.html(
        returns=returns,
        benchmark=benchmark,
        strategy_label="RELIANCE",
        benchmark_label="NIFTY",
        title="Detailed Nubra Report",
        output=str(output),
        mode="detailed",
    )
    assert Path(path).exists()
    content = Path(path).read_text(encoding="utf-8")
    assert "Detailed Nubra Report" in content
    assert "Key Performance Metrics" in content
    assert "Worst Drawdowns" in content


def test_basic_converts_benchmark_returns_to_equity_for_plot(monkeypatch):
    returns = pd.Series(
        [0.0, 0.01, -0.02, 0.005],
        index=pd.date_range("2026-01-01", periods=4, freq="D"),
    )
    equity = (1.0 + returns).cumprod() * 100000.0
    benchmark_returns = returns * 0.5

    captured: dict[str, pd.Series | None] = {"benchmark": None}

    def _fake_equity_curve(eq, benchmark=None, **kwargs):  # noqa: ANN001
        captured["benchmark"] = benchmark
        return None

    monkeypatch.setattr(reports.plots, "equity_curve", _fake_equity_curve)
    monkeypatch.setattr(reports.plots, "drawdown", lambda *args, **kwargs: None)
    monkeypatch.setattr(reports.plots, "monthly_heatmap", lambda *args, **kwargs: None)

    reports.basic(
        returns=returns,
        equity=equity,
        benchmark=benchmark_returns,
        display=False,
        show_plots=True,
    )

    bench_eq = captured["benchmark"]
    assert bench_eq is not None
    assert float(bench_eq.iloc[0]) == 100000.0
    assert float(bench_eq.iloc[-1]) > 0.0
