from __future__ import annotations

import pandas as pd

import nubrastats as ns


def main() -> None:
    # Replace this with your own Nubra-derived return series.
    returns = pd.Series(
        [0.01, -0.004, 0.006, 0.002, -0.008, 0.012, 0.004, -0.001, 0.003, 0.005],
        index=pd.date_range("2025-01-01", periods=10, freq="D"),
    )
    benchmark = returns * 0.65

    out = ns.reports.html(
        returns=returns,
        benchmark=benchmark,
        strategy_label="RELIANCE",
        benchmark_label="NIFTY",
        title="Nubra Detailed Demo Report",
        output="nubrastats-detailed-demo.html",
        mode="detailed",
    )
    print("Detailed report generated:", out)


if __name__ == "__main__":
    main()
