# nubrastats

`nubrastats` is a Nubra-native helper library for:

- stock performance analytics
- portfolio performance analytics using symbol + quantity inputs
- performance plots
- HTML tearsheet reports
- Nubra API historical data parsing
- Nubra order/trade payload normalization

It is designed so users can fetch market data from Nubra and generate metrics/reports
with minimal code.

## What This Library Does

Standard workflows:

Single-stock workflow:

1. Fetch close prices from Nubra Historical API (`nubrastats.nubra`)
2. Convert prices to returns (`nubrastats.utils.to_returns`)
3. Compute performance metrics (`nubrastats.stats`)
4. Generate charts (`nubrastats.plots`)
5. Export terminal/HTML reports (`nubrastats.reports`)

Portfolio workflow:

1. Fetch close prices for multiple Nubra symbols
2. Use symbol quantities plus first-date prices to derive start weights
3. Build portfolio value, returns, and equity curve
4. Compare portfolio against optional benchmark
5. Export terminal/HTML reports and plots

Alternative workflow:

1. Convert filled order payloads to trade rows (`nubrastats.adapters.orders_to_trades`)
2. Compute realized FIFO PnL (`nubrastats.adapters.realized_pnl_fifo`)
3. Build equity and returns from trades
4. Run the same stats/plots/reports pipeline

## Installation

Install from PyPI:

```bash
pip install nubrastats
```

If you use Nubra API fetch helpers, install Nubra SDK too:

```bash
pip install nubra-sdk
```

Local editable install:

```bash
cd nubra-stats
pip install -e .[dev]
```

## Packaging Notes

- The published package is Nubra-only (`nubrastats`).
- Example scripts in `examples/` are for local development and are excluded from release artifacts.
- Release artifacts include:
  - library source under `src/nubrastats`
  - HTML templates under `src/nubrastats/templates`
  - project metadata (`pyproject.toml`, `README.md`, `LICENSE`)

## Quick Start (Minimal)

```python
import pandas as pd
import nubrastats as ns

returns = pd.Series([0.01, -0.005, 0.007, 0.002])
ns.reports.metrics(returns=returns, display=True)
ns.reports.html(returns=returns, title="Demo", output="demo-report.html")
# detailed tearsheet mode (extended metrics + multi-section charts)
ns.reports.html(
    returns=returns,
    title="Demo Detailed",
    output="demo-detailed-report.html",
    mode="detailed",
)
```

## Quick Start (Nubra API -> Report)

```python
from nubra_python_sdk.marketdata.market_data import MarketData
from nubra_python_sdk.start_sdk import InitNubraSdk, NubraEnv
import pandas as pd
import nubrastats as ns

nubra = InitNubraSdk(env=NubraEnv.UAT, env_creds=True, totp_login=False)
md = MarketData(nubra)

prices = ns.nubra.fetch_close_series(
    md_client=md,
    symbol="RELIANCE",
    exchange="NSE",
    instrument_type="STOCK",
    start="2025-01-01",
    end="2025-12-31",
    interval="1d",
)

returns = ns.utils.to_series(ns.utils.to_returns(prices)).dropna()
ns.reports.metrics(returns=returns, display=True)
ns.reports.html(returns=returns, title="RELIANCE Report", output="reliance_report.html")
ns.reports.html(
    returns=returns,
    benchmark=returns * 0.8,  # replace with actual benchmark returns
    title="RELIANCE Detailed Report",
    output="reliance_detailed_report.html",
    mode="detailed",
)
```

## Quick Start (One Call, Minimal User Code)

```python
from nubra_python_sdk.marketdata.market_data import MarketData
from nubra_python_sdk.start_sdk import InitNubraSdk, NubraEnv
import nubrastats as ns

nubra = InitNubraSdk(env=NubraEnv.UAT, env_creds=True)
md = MarketData(nubra)

result = ns.nubra.analyze_symbol(
    md_client=md,
    symbol="RELIANCE",
    exchange="NSE",
    instrument_type="STOCK",
    start="2025-01-01",
    end="2025-12-31",
    interval="1d",
    benchmark_symbol="NIFTY",          # optional
    show_plots=True,                    # pop up plots
    save_plots=False,                   # optional PNG save
    generate_html=True,                 # optional HTML report
    open_html=True,                     # optional browser auto-open
    html_output="reliance_report.html",
    html_mode="detailed",               # "basic" | "detailed"
)
```

In generated metrics/HTML, the strategy and benchmark are labeled using the
actual symbols (for example `RELIANCE` and `NIFTY`) instead of generic names.
The equity curve represents compounded notional capital (base `100000`) from
periodic returns, not raw stock price.

## Quick Start (Portfolio)

```python
from nubra_python_sdk.marketdata.market_data import MarketData
from nubra_python_sdk.start_sdk import InitNubraSdk, NubraEnv
import nubrastats as ns

nubra = InitNubraSdk(env=NubraEnv.PROD, env_creds=True)
md = MarketData(nubra)

result = ns.nubra.analyze_portfolio(
    md_client=md,
    positions=[
        {"symbol": "RELIANCE", "exchange": "NSE", "instrument_type": "STOCK", "quantity": 2},
        {"symbol": "IDEA", "exchange": "NSE", "instrument_type": "STOCK", "quantity": 5},
    ],
    portfolio_name="My Portfolio",
    start="2025-01-01",
    end="2025-12-31",
    interval="1d",
    benchmark_symbol="NIFTY",
    show_plots=True,
    generate_html=True,
    html_mode="detailed",
)
```

Portfolio weights are derived from:

- `quantity * first available price` for each symbol
- then normalized into start-date portfolio weights

This means the portfolio report reflects the quantity mix entered by the user, not equal weights unless the quantities and prices imply that.

## Quick Start (Popup UI)

If you want users to only call one function and fill details in a popup:

```python
import nubrastats as ns

ns.ui.launch_analyzer_ui()
```

This opens a popup UI for:

- primary stock analysis inputs
- optional portfolio mode with multiple symbols + quantity
- date range (calendar picker) and interval
- benchmark options
- plot popup options
- optional PNG/HTML output options
- configurable Risk-Free Rate (%) field

After clicking **Generate Report**, the library handles authentication, analysis, and report generation internally.

UI behavior:

- when only primary symbol mode is used, the generated HTML title defaults to `Nubra Stock Analysis`
- when portfolio mode is enabled, the generated HTML title defaults to `Nubra Portfolio Report`
- stock/instrument inputs are forced to uppercase in the UI
- UI instrument dropdowns are limited to `STOCK` and `INDEX`

`.env` credential note for popup/auth flows:

- keep a `.env` file in project root or `examples/.env`
- use keys exactly: `PHONE_NO` and `MPIN`
- recommended format:
  - `PHONE_NO="9999999999"`
  - `MPIN="1234"`

If credentials are missing, the popup UI now asks for phone / OTP / TOTP / MPIN in modal dialogs instead of waiting silently in the terminal.

When popup plot display is enabled, charts open in one viewer with **Previous/Next**
navigation and keyboard arrow support.

## Input Conventions

- `returns` are decimal returns per period, not percentage.
  - Example: `0.01` means `+1%`.
- `prices` and `equity` should be `pandas.Series` with datetime index.
- Nubra historical close values are treated as paise and converted to rupees
  (`price_scale="paise"` default in `nubrastats.nubra.fetch_close_series`).
- Trade prices/fees from broker payloads may be paise-based.
  - `adapters.orders_to_trades(..., price_scale="paise")` converts to rupees.

## Public API Reference

## Top-Level Package (`nubrastats`)

- `nubrastats.__version__`
- `nubrastats.extend_pandas()`
- modules:
  - `nubrastats.nubra`
  - `nubrastats.adapters`
  - `nubrastats.utils`
  - `nubrastats.stats`
  - `nubrastats.plots`
  - `nubrastats.reports`
  - `nubrastats.ui`

`extend_pandas()` adds methods to pandas objects:

- `ns_to_returns`
- `ns_to_equity`
- `ns_sharpe`
- `ns_sortino`
- `ns_cagr`
- `ns_max_drawdown`
- `ns_drawdown_series`

## Module: `nubrastats.nubra`

Purpose: build Nubra historical request payloads and extract close price series.

### Constants

- `NUBRA_INTERVALS = {"1s","1m","2m","3m","5m","15m","30m","1h","1d","1w","1mt"}`
- `NUBRA_TYPES = {"STOCK","INDEX","OPT","FUT"}`

### Dataclass: `Instrument`

| Field | Type | Default |
|---|---|---|
| `symbol` | `str` | required |
| `exchange` | `str` | `"NSE"` |
| `instrument_type` | `str` | `"STOCK"` |

### Functions

### `to_utc_iso(value: str | pd.Timestamp) -> str`

Converts input datetime to UTC ISO string ending with `Z`.

Parameters:

- `value`: date/time string or `pd.Timestamp`

### `build_historical_payload(...) -> dict[str, Any]`

Signature:

```python
build_historical_payload(
    *,
    symbol: str,
    exchange: str,
    instrument_type: str,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    interval: str = "1d",
    fields: list[str] | None = None,
) -> dict[str, Any]
```

Parameters:

- `symbol`: instrument symbol
- `exchange`: exchange name, e.g. `"NSE"`
- `instrument_type`: one of `STOCK/INDEX/OPT/FUT`
- `start`: start date/time
- `end`: end date/time
- `interval`: one of Nubra supported intervals above
- `fields`: API fields list; defaults to `["close"]`

Returns:

- request payload dict for `MarketData.historical_data`

### `close_series_from_historical_response(response, symbol) -> pd.Series`

Extracts close prices from Nubra historical response object for one symbol.

Parameters:

- `response`: object returned by `md_client.historical_data(...)`
- `symbol`: symbol to extract

Returns:

- close-price `pd.Series` indexed by timestamp

### `fetch_close_series(...) -> pd.Series`

Signature:

```python
fetch_close_series(
    md_client: Any,
    *,
    symbol: str,
    exchange: str = "NSE",
    instrument_type: str = "STOCK",
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    interval: str = "1d",
) -> pd.Series
```

Parameters:

- `md_client`: Nubra `MarketData` instance
- `symbol`, `exchange`, `instrument_type`: instrument identity
- `start`, `end`: date bounds
- `interval`: candle interval

Returns:

- filtered close-price `pd.Series` for the selected range

Raises:

- `ValueError` when no data is available or invalid date interval

### `analyze_symbol(...) -> dict[str, Any]`

One-call convenience pipeline for minimal user code:

1. fetch primary symbol historical close
2. optional benchmark fetch and alignment
3. compute returns/equity
4. compute metrics
5. show plots immediately (`show_plots=True`)
6. optionally save PNGs (`save_plots=True`)
7. optionally generate HTML report (`generate_html=True`)
8. optionally auto-open HTML (`open_html=True`)

Signature:

```python
analyze_symbol(
    md_client: Any,
    *,
    symbol: str,
    exchange: str = "NSE",
    instrument_type: str = "STOCK",
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    interval: str = "1d",
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
) -> dict[str, Any]
```

Returns dictionary keys:

- `prices`, `returns`, `equity`
- `benchmark_prices`, `benchmark_returns`, `benchmark_equity`
- `metrics` (DataFrame)
- `plot_paths` (empty unless `save_plots=True`)
- `html_path` (`None` unless `generate_html=True`)
- `html_opened` (`True` if browser auto-open succeeded)
- `html_mode` (`"basic"` or `"detailed"`)

### `analyze_portfolio(...) -> dict[str, Any]`

One-call portfolio pipeline for multiple symbols and quantities.

Behavior:

1. normalize portfolio items
2. fetch close prices for each symbol
3. align dates across symbols
4. compute start-date value from `quantity * first price`
5. derive portfolio weights
6. build portfolio value, returns, equity, and optional benchmark comparison
7. generate plots and HTML report just like single-symbol flow

Important input rule:

- quantity must be greater than `0` for every portfolio item
- duplicate symbol/exchange/type rows are rejected

Returns dictionary keys include:

- `prices` / `component_prices`
- `returns`, `equity`
- `portfolio_items`
- `portfolio_weights`
- `metrics`
- `benchmark_prices`, `benchmark_returns`, `benchmark_equity`
- `html_path`, `html_opened`, `plot_paths`

## Module: `nubrastats.ui`

Purpose: popup-based minimal UX for end users (no manual plumbing code).

### Dataclass: `AnalyzerUIConfig`

Holds all UI/run configuration fields such as:

- environment + login flags
- primary symbol settings
- portfolio settings (`portfolio_enabled`, `portfolio_name`, `portfolio_items`)
- benchmark settings
- plot/report options
- `risk_free_rate` (UI default `6.0`, interpreted as percent)

### `run_from_config(config, *, md_client=None) -> dict[str, Any]`

Runs analysis directly from a config object.

Parameters:

- `config`: `AnalyzerUIConfig`
- `md_client`: optional pre-created Nubra `MarketData` client

Returns:

- same output dictionary as `nubrastats.nubra.analyze_symbol`

### `launch_analyzer_ui(initial=None) -> None`

Opens the popup UI and executes analysis when user clicks **Generate Report**.

Parameters:

- `initial`: optional `AnalyzerUIConfig` to prefill defaults

## Module: `nubrastats.adapters`

Purpose: convert broker/order payloads into consistent trade tables and PnL.

### `orders_to_trades(orders, *, price_scale="paise") -> pd.DataFrame`

Parameters:

- `orders`: iterable of order dicts
- `price_scale`: `"paise"` or raw-unscaled mode

Reads these possible keys from each order:

- quantity keys: `filled_qty`, `order_qty`, `trade_qty`, `quantity`
- price keys: `avg_filled_price`, `trade_price`, `order_price`, `price`, `last_traded_price`
- side keys: `order_side`, `side`
- timestamp keys: `filled_time`, `order_time`, `last_modified`, `timestamp`
- fee keys: `brokerage`, `fee`, `charges`

Output columns:

- `timestamp`, `symbol`, `side`, `quantity`, `price`, `fee`,
  `order_id`, `tag`, `strategy_id`, `status`

### `realized_pnl_fifo(trades: pd.DataFrame) -> pd.DataFrame`

Computes realized PnL using per-symbol FIFO lot matching.
Supports long and short inventory transitions.

Required columns:

- `timestamp`, `symbol`, `side`, `quantity`, `price`

Optional:

- `fee` (defaults to `0.0`)

Adds columns:

- `realized_pnl`
- `cum_realized_pnl`

### `equity_curve_from_trades(trades, *, starting_capital=100000.0) -> pd.Series`

If `realized_pnl` is missing, it computes it first via FIFO.
Then cumulative sum over realized PnL on top of starting capital.

### `returns_from_trades(trades, *, starting_capital=100000.0) -> pd.Series`

Builds equity curve from trades and converts it to period returns.

## Module: `nubrastats.utils`

Purpose: reusable conversion/index/time helpers.

### `to_series(data) -> pd.Series`

Parameters:

- `data`: `pd.Series`, `pd.DataFrame`, or iterable

Returns:

- one `pd.Series` (for DataFrame takes first column)

### `ensure_datetime_index(data, *, fallback_start=None, freq="D")`

Ensures datetime index. If conversion fails, generates date range index.

### `to_returns(equity) -> pd.Series | pd.DataFrame`

Converts equity/price series to returns via `pct_change`.

### `to_equity(returns, *, start_balance=100000.0)`

Compounds returns into equity series.

### `annualization_factor(periods_per_year=252) -> int`

Returns a safe annualization factor (min `1`).

### `safe_div(numerator, denominator) -> float`

Returns `NaN` if denominator is zero or NaN.

### `monthly_returns_matrix(returns: pd.Series) -> pd.DataFrame`

Pivoted matrix: index `year`, columns `Jan..Dec`, values monthly compounded returns.

### `normalize_side(value: str) -> str`

Maps side aliases to standard:

- BUY aliases: `BUY`, `ORDER_SIDE_BUY`, `B`
- SELL aliases: `SELL`, `ORDER_SIDE_SELL`, `S`

### `to_timestamp(value) -> pd.Timestamp`

Converts int/float/string timestamps.
For numeric values, tries:

- nanoseconds if very large
- milliseconds
- seconds

## Module: `nubrastats.stats`

Purpose: performance metrics from returns/equity/trades.

### `comp(returns) -> float | pd.Series`

Compounded return: `prod(1 + r) - 1`.

### `cagr(returns, periods_per_year=252) -> float`

Annualized compounded growth rate.

### `volatility(returns, periods_per_year=252, annualize=True) -> float`

Sample standard deviation; annualized if requested.

### `sharpe(returns, rf=0.06, periods_per_year=252) -> float`

Sharpe ratio using per-period risk-free conversion.

### `sortino(returns, rf=0.06, periods_per_year=252) -> float`

Sortino ratio using downside deviation only.

### `drawdown_series(returns=None, equity=None) -> pd.Series`

Drawdown over time: `equity / cummax(equity) - 1`.
Either `returns` or `equity` must be provided.

### `max_drawdown(returns=None, equity=None) -> float`

Minimum value of drawdown series.

### `win_rate_returns(returns) -> float`

Fraction of positive non-zero return periods.

### `win_rate_trades(trades) -> float`

Fraction of positive non-zero trade PnL rows.
Uses `realized_pnl` column when available, otherwise `pnl`.

### `profit_factor(trades) -> float`

`sum(winning pnl) / abs(sum(losing pnl))`.

### `expectancy(trades) -> float`

Mean trade PnL.

### `summary(...) -> pd.Series`

Signature:

```python
summary(
    *,
    returns: pd.Series | None = None,
    equity: pd.Series | None = None,
    trades: pd.DataFrame | None = None,
    rf: float = 0.06,
    periods_per_year: int = 252,
) -> pd.Series
```

Returns these keys:

- `Total Return`
- `CAGR`
- `Volatility`
- `Sharpe`
- `Sortino`
- `Max Drawdown`
- `Win Rate (Periods)`
- `Avg Return`
- `Best Period`
- `Worst Period`

If trades provided, also:

- `Win Rate (Trades)`
- `Profit Factor`
- `Expectancy`
- `Trade Count`

## Module: `nubrastats.plots`

Purpose: plotting helpers using matplotlib/seaborn.

All plotting functions return `matplotlib.figure.Figure`.
Most functions support:

- `show=True/False`
- `savefig={...}` passed to `fig.savefig`

By default, plots are displayed when `show=True`.
Saving PNG files is optional via `savefig` or higher-level helpers.

### `equity_curve(equity, benchmark=None, *, title="Equity Curve", show=True, savefig=None)`

Plots strategy equity and optional benchmark equity.

### `drawdown(returns=None, equity=None, *, title="Drawdown", show=True, savefig=None)`

Filled drawdown chart from returns or equity.

### `monthly_heatmap(returns, *, title="Monthly Returns Heatmap", show=True, savefig=None)`

Year-month heatmap in percentage terms.

### `pnl_distribution(trades, *, title="Trade PnL Distribution", show=True, savefig=None)`

Histogram/KDE of trade PnL (`realized_pnl` or `pnl`).

### `rolling_sharpe(returns, *, window=63, rf=0.0, periods_per_year=252, title="Rolling Sharpe", show=True, savefig=None)`

Rolling Sharpe time series plot.

### `figure_to_png_bytes(fig) -> bytes`

Encodes a figure as PNG bytes (used by HTML report embedding).

## Module: `nubrastats.reports`

Purpose: ready-to-use metrics tables and report generation.

### `metrics(...) -> pd.DataFrame`

Signature:

```python
metrics(
    *,
    returns: pd.Series | None = None,
    equity: pd.Series | None = None,
    trades: pd.DataFrame | None = None,
    benchmark: pd.Series | None = None,
    rf: float = 0.06,
    periods_per_year: int = 252,
    display: bool = True,
    precision: int = 4,
) -> pd.DataFrame
```

Behavior:

- computes summary metrics for strategy
- optional benchmark summary in second column
- prints table if `display=True`

### `basic(...) -> pd.DataFrame`

Same metric inputs as `metrics` plus:

- `show_plots: bool = True`

Behavior:

- prints metrics
- optional standard plot set (equity/drawdown/monthly heatmap)

### `full(...) -> pd.DataFrame`

Same parameters as `basic`.

Behavior:

- includes `basic` metrics
- adds rolling Sharpe and PnL distribution (if trades provided)

### `html(...) -> str`

Signature:

```python
html(
    *,
    returns: pd.Series | None = None,
    equity: pd.Series | None = None,
    trades: pd.DataFrame | None = None,
    benchmark: pd.Series | None = None,
    rf: float = 0.06,
    periods_per_year: int = 252,
    title: str = "Nubra Strategy Tearsheet",
    output: str | None = None,
    template_path: str | None = None,
    mode: str = "basic",
) -> str
```

Behavior:

- `mode="basic"`: compact report (metrics + core charts)
- `mode="detailed"`: extended tearsheet (multi-section charts + advanced tables)
- writes file to `output`:
  - basic default: `nubrastats-report.html`
  - detailed default: `nubrastats-detailed-report.html`

Returns:

- output file path string

## Module: `nubrastats.models`

Simple typed dataclasses:

### `Trade`

| Field | Type | Required | Default |
|---|---|---|---|
| `timestamp` | `datetime` | yes | - |
| `symbol` | `str` | yes | - |
| `side` | `str` | yes | - |
| `quantity` | `float` | yes | - |
| `price` | `float` | yes | - |
| `fee` | `float` | no | `0.0` |
| `strategy_id` | `str | None` | no | `None` |
| `tag` | `str | None` | no | `None` |

### `OrderEvent`

| Field | Type | Required | Default |
|---|---|---|---|
| `timestamp` | `datetime` | yes | - |
| `order_id` | `str | int` | yes | - |
| `symbol` | `str` | yes | - |
| `side` | `str` | yes | - |
| `quantity` | `float` | yes | - |
| `price` | `float` | yes | - |
| `status` | `str` | yes | - |
| `tag` | `str | None` | no | `None` |

## Example Scripts Included

| Script | Purpose |
|---|---|
| `examples/import_smoke.py` | import/version smoke test |
| `examples/generate_report.py` | sample report generation from sample trades |
| `examples/terminal_menu_tester.py` | interactive Nubra terminal flow |
| `examples/nubra_api_static_test.py` | non-interactive QA/checklist runner |
| `examples/nubra_api_quick_test.py` | short placeholder-based run script |
| `examples/detailed_report_mode_demo.py` | generate extended HTML tearsheet (`mode="detailed"`) |
| `examples/nubra_ui_popup_demo.py` | one-function popup UI launcher |

## Testing and Quality

Run checks:

```bash
python -m ruff check src tests examples
python -m pytest
```

Build package:

```bash
python -m build
python -m twine check dist/*
```

## Notes

- The quick script is for minimal user lines.
- The static script is intentionally larger for diagnostics and validation checks.
- This project is Nubra-native and does not depend on external market-data providers.
- Popup UI currently defaults Risk-Free Rate to `6%`, but users can override it.
- Detailed HTML report is the default mode in the popup UI.
- Portfolio mode in the popup UI generates `Nubra Portfolio Report`; single-symbol mode generates `Nubra Stock Analysis` by default.
