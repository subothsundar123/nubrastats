from __future__ import annotations

from nubra_python_sdk.marketdata.market_data import MarketData
from nubra_python_sdk.start_sdk import InitNubraSdk, NubraEnv

import nubrastats as ns

# ============================================================================
# USER PLACEHOLDERS (EDIT ONLY THIS SECTION)
# ============================================================================
ENV = NubraEnv.UAT
USE_ENV_CREDS = True
USE_TOTP_LOGIN = False

START_DATE = "2025-01-01"
END_DATE = "2025-12-31"
INTERVAL = "1d"

PRIMARY = {"symbol": "RELIANCE", "exchange": "NSE", "instrument_type": "STOCK"}

ENABLE_BENCHMARK = True
BENCHMARK = {"symbol": "NIFTY", "exchange": "NSE", "instrument_type": "INDEX"}

SHOW_PLOTS = True  # pop up charts
SAVE_PNG = False  # optional: save plots as PNG
PLOTS_DIR = "quick_plots"

GENERATE_HTML = True  # optional: generate html report
OPEN_HTML_REPORT = True  # optional: auto-open HTML in browser
REPORT_OUTPUT = "quick_nubra_report.html"


def main() -> None:
    nubra = InitNubraSdk(env=ENV, env_creds=USE_ENV_CREDS, totp_login=USE_TOTP_LOGIN)
    md = MarketData(nubra)

    result = ns.nubra.analyze_symbol(
        md,
        start=START_DATE,
        end=END_DATE,
        interval=INTERVAL,
        benchmark_symbol=BENCHMARK["symbol"] if ENABLE_BENCHMARK else None,
        benchmark_exchange=BENCHMARK["exchange"],
        benchmark_instrument_type=BENCHMARK["instrument_type"],
        show_plots=SHOW_PLOTS,
        save_plots=SAVE_PNG,
        plots_dir=PLOTS_DIR,
        generate_html=GENERATE_HTML,
        open_html=OPEN_HTML_REPORT,
        html_output=REPORT_OUTPUT,
        title=f"{PRIMARY['symbol']} Nubra Quick Report",
        display_metrics=True,
        **PRIMARY,
    )
    if result["html_path"] is not None:
        print(f"Generated report: {result['html_path']}")
        if result["html_opened"]:
            print("Opened report in browser.")
    if result["plot_paths"]:
        print("Saved plot files:")
        for _, path in result["plot_paths"].items():
            print(path)


if __name__ == "__main__":
    main()
