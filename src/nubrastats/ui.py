from __future__ import annotations

import builtins
import os
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any

from . import nubra, plots

_ENV_NAMES = ("UAT", "PROD", "DEV", "STAGING")
_INTERVAL_ORDER = ("1s", "1m", "2m", "3m", "5m", "15m", "30m", "1h", "1d", "1w", "1mt")
_UI_INSTRUMENT_TYPES = ("STOCK", "INDEX")


@dataclass(slots=True)
class AnalyzerUIConfig:
    env: str = "PROD"
    use_env_creds: bool = True
    use_totp_login: bool = False

    symbol: str = "RELIANCE"
    exchange: str = "NSE"
    instrument_type: str = "STOCK"
    portfolio_enabled: bool = False
    portfolio_name: str = "My Portfolio"
    portfolio_items: list[dict[str, Any]] = field(default_factory=list)
    start: str = "2025-01-01"
    end: str = "2025-12-31"
    interval: str = "1d"

    benchmark_enabled: bool = True
    benchmark_symbol: str = "NIFTY"
    benchmark_exchange: str = "NSE"
    benchmark_instrument_type: str = "INDEX"

    show_plots: bool = True
    save_plots: bool = False
    plots_dir: str = "nubrastats-plots"

    generate_html: bool = True
    open_html: bool = True
    html_output: str = "nubrastats-ui-report.html"
    html_mode: str = "detailed"
    title: str = "Nubra UI Report"

    display_metrics: bool = True
    risk_free_rate: float = 6.0


@dataclass(slots=True)
class PortfolioItem:
    symbol: str
    quantity: float
    exchange: str = "NSE"
    instrument_type: str = "STOCK"


def _to_date_or_fallback(value: str, fallback: date) -> date:
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return fallback


def _resolve_env_file() -> Path | None:
    candidates = [
        Path.cwd() / ".env",
        Path.cwd() / "examples" / ".env",
        Path(__file__).resolve().parents[2] / "examples" / ".env",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _load_env_file(path: Path) -> int:
    loaded = 0
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value
        loaded += 1
    return loaded


def _seed_env_aliases() -> None:
    phone = os.environ.get("PHONE_NO") or os.environ.get("phone")
    mpin = os.environ.get("MPIN") or os.environ.get("mpin")
    if phone:
        os.environ["PHONE_NO"] = phone
        os.environ["phone"] = phone
    if mpin:
        os.environ["MPIN"] = mpin
        os.environ["mpin"] = mpin


def _bind_uppercase_var(var: Any) -> None:
    def _normalize(*_args: Any) -> None:
        value = var.get()
        upper = str(value).upper()
        if value != upper:
            var.set(upper)

    var.trace_add("write", _normalize)


def _build_plot_figures(result: dict[str, Any], *, symbol: str) -> list[tuple[str, Any]]:
    returns = result.get("returns")
    equity = result.get("equity")
    if returns is None or equity is None:
        return []

    symbol_name = str(result.get("strategy_label") or symbol).strip().upper() or "SYMBOL"
    benchmark_equity = result.get("benchmark_equity")
    return [
        (
            "Equity Curve",
            plots.equity_curve(
                equity,
                benchmark=benchmark_equity,
                title=f"{symbol_name} Equity Curve",
                show=False,
            ),
        ),
        (
            "Drawdown",
            plots.drawdown(
                equity=equity,
                title=f"{symbol_name} Drawdown",
                show=False,
            ),
        ),
        (
            "Monthly Returns",
            plots.monthly_heatmap(
                returns,
                title=f"{symbol_name} Monthly Returns",
                show=False,
            ),
        ),
        (
            "Rolling Sharpe",
            plots.rolling_sharpe(
                returns,
                title=f"{symbol_name} Rolling Sharpe",
                show=False,
            ),
        ),
    ]


def _open_plot_navigator(parent: Any, figures: list[tuple[str, Any]]) -> None:
    import tkinter as tk
    from tkinter import ttk

    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

    if not figures:
        return

    viewer = tk.Toplevel(parent)
    viewer.title("NubraStats Plot Viewer")
    viewer.geometry("1050x720")
    viewer.minsize(840, 560)

    index = tk.IntVar(value=0)
    title_var = tk.StringVar(value="")
    canvas_state: dict[str, FigureCanvasTkAgg | None] = {"canvas": None}

    controls = ttk.Frame(viewer, padding=(10, 10, 10, 0))
    controls.pack(fill=tk.X)
    ttk.Button(controls, text="< Previous", command=lambda: _step(-1)).pack(side=tk.LEFT)
    ttk.Button(controls, text="Next >", command=lambda: _step(1)).pack(side=tk.LEFT, padx=(8, 0))
    ttk.Label(controls, textvariable=title_var, font=("Segoe UI", 10, "bold")).pack(
        side=tk.LEFT, padx=(14, 0)
    )
    close_btn = ttk.Button(controls, text="Close")
    close_btn.pack(side=tk.RIGHT)

    canvas_wrap = ttk.Frame(viewer, padding=10)
    canvas_wrap.pack(fill=tk.BOTH, expand=True)

    def _render() -> None:
        idx = index.get()
        plot_title, fig = figures[idx]
        title_var.set(f"{idx + 1}/{len(figures)} - {plot_title}")
        current = canvas_state["canvas"]
        if current is not None:
            current.get_tk_widget().destroy()
        canvas = FigureCanvasTkAgg(fig, master=canvas_wrap)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        canvas_state["canvas"] = canvas
        viewer.focus_set()

    def _step(delta: int) -> None:
        index.set((index.get() + delta) % len(figures))
        _render()

    def _on_close() -> None:
        for _, fig in figures:
            plt.close(fig)
        viewer.destroy()

    close_btn.configure(command=_on_close)
    viewer.bind("<Left>", lambda _event: _step(-1))
    viewer.bind("<Right>", lambda _event: _step(1))
    viewer.protocol("WM_DELETE_WINDOW", _on_close)
    _render()



@dataclass(slots=True)
class _PromptContext:
    env: str
    use_env_creds: bool
    use_totp_login: bool
    phone: str | None = None
    mpin: str | None = None


def _prompt_title(prompt: str) -> str:
    raw = prompt.lower()
    if "otp" in raw and "totp" not in raw:
        return "Enter OTP"
    if "totp" in raw:
        return "Enter TOTP"
    if "mpin" in raw or "pin" in raw:
        return "Enter MPIN"
    if "phone" in raw:
        return "Enter Phone Number"
    if "password" in raw:
        return "Enter Password"
    return "Enter Value"


def _prompt_label(prompt: str) -> str:
    clean = " ".join(str(prompt).strip().split())
    return clean or "Enter value"


def _initial_prompt_value(prompt: str, ctx: _PromptContext) -> str:
    raw = prompt.lower()
    if "phone" in raw and ctx.phone:
        return ctx.phone
    if ("mpin" in raw or "pin" in raw) and ctx.mpin:
        return ctx.mpin
    return ""


def _should_mask_prompt(prompt: str) -> bool:
    raw = prompt.lower()
    return any(token in raw for token in ("otp", "totp", "mpin", "pin", "password"))


def _friendly_error_message(exc: Exception) -> str:
    message = str(exc).strip()
    prefix_map = {
        "Primary symbol failed:": "Invalid or unavailable primary symbol entered",
        "Benchmark symbol failed:": "Invalid or unavailable benchmark symbol entered",
        "Portfolio symbol failed:": "Invalid or unavailable portfolio symbol entered",
    }
    for prefix, label in prefix_map.items():
        if message.startswith(prefix):
            rest = message[len(prefix):].strip()
            symbol_part, sep, detail = rest.partition('.')
            symbol_text = symbol_part.strip()
            if sep:
                detail = detail.strip()
            else:
                detail = ""
            lines = [f"{label}: {symbol_text}"]
            if detail:
                lines.append("")
                lines.append(detail)
            return "\n".join(lines)
    return message


def _prompt_popup(parent: Any, prompt: str, *, ctx: _PromptContext) -> str:
    import tkinter as tk
    from tkinter import ttk

    top = tk.Toplevel(parent)
    top.title(_prompt_title(prompt))
    top.transient(parent)
    top.grab_set()
    top.resizable(False, False)
    top.geometry("430x190")
    top.minsize(430, 190)

    value_var = tk.StringVar(value=_initial_prompt_value(prompt, ctx))
    result: dict[str, str | None] = {"value": None}

    wrap = ttk.Frame(top, padding=16)
    wrap.pack(fill=tk.BOTH, expand=True)
    ttk.Label(
        wrap,
        text="Nubra login requires additional input to continue.",
        font=("Segoe UI", 10, "bold"),
        wraplength=380,
    ).pack(anchor="w", pady=(0, 10))
    ttk.Label(wrap, text=_prompt_label(prompt), wraplength=380).pack(anchor="w")
    entry = ttk.Entry(wrap, textvariable=value_var, width=34)
    if _should_mask_prompt(prompt):
        entry.configure(show="*")
    entry.pack(anchor="w", fill=tk.X, pady=(8, 10))

    note = "This prompt came from Nubra authentication."
    if "phone" in prompt.lower():
        note = "Enter the phone number linked to your Nubra account."
    elif "otp" in prompt.lower() and "totp" not in prompt.lower():
        note = "Enter the OTP received on your phone."
    elif "totp" in prompt.lower():
        note = "Enter the current authenticator TOTP code."
    elif "mpin" in prompt.lower() or "pin" in prompt.lower():
        note = "Enter your Nubra MPIN."
    ttk.Label(wrap, text=note, foreground="#555555", wraplength=380).pack(anchor="w")

    btns = ttk.Frame(wrap)
    btns.pack(anchor="e", pady=(12, 0), fill=tk.X)

    def _submit() -> None:
        value = value_var.get().strip()
        if not value:
            return
        result["value"] = value
        top.destroy()

    def _cancel() -> None:
        top.destroy()

    ttk.Button(btns, text="Cancel", command=_cancel).pack(side=tk.RIGHT)
    ttk.Button(btns, text="Continue", command=_submit).pack(side=tk.RIGHT, padx=(0, 8))
    top.bind("<Return>", lambda _event: _submit())
    top.bind("<Escape>", lambda _event: _cancel())
    entry.focus_set()
    top.wait_window()

    if result["value"] is None:
        raise ValueError("Authentication cancelled by user")

    value = str(result["value"])
    raw = prompt.lower()
    if "phone" in raw:
        ctx.phone = value
        os.environ["PHONE_NO"] = value
        os.environ["phone"] = value
    elif "mpin" in raw or "pin" in raw:
        ctx.mpin = value
        os.environ["MPIN"] = value
        os.environ["mpin"] = value
    return value


@contextmanager
def _patch_sdk_prompts(*, parent: Any, ctx: _PromptContext):
    original_input = builtins.input

    def _popup_input(prompt: str = "") -> str:
        return _prompt_popup(parent, prompt, ctx=ctx)

    builtins.input = _popup_input
    try:
        yield
    finally:
        builtins.input = original_input


def _create_market_data_client(
    *,
    env: str,
    use_env_creds: bool,
    use_totp_login: bool,
    prompt_parent: Any | None = None,
) -> Any:
    from nubra_python_sdk.marketdata.market_data import MarketData
    from nubra_python_sdk.start_sdk import InitNubraSdk, NubraEnv

    env_key = env.strip().upper()
    env_map = {
        "UAT": NubraEnv.UAT,
        "PROD": NubraEnv.PROD,
        "DEV": NubraEnv.DEV,
        "STAGING": NubraEnv.STAGING,
    }
    if env_key not in env_map:
        raise ValueError(f"env must be one of {sorted(env_map.keys())}")

    if use_env_creds:
        env_file = _resolve_env_file()
        if env_file is not None:
            _load_env_file(env_file)
        _seed_env_aliases()

    ctx = _PromptContext(
        env=env_key,
        use_env_creds=use_env_creds,
        use_totp_login=use_totp_login,
        phone=os.environ.get("PHONE_NO") or os.environ.get("phone"),
        mpin=os.environ.get("MPIN") or os.environ.get("mpin"),
    )

    if prompt_parent is not None:
        with _patch_sdk_prompts(parent=prompt_parent, ctx=ctx):
            sdk = InitNubraSdk(
                env=env_map[env_key],
                env_creds=use_env_creds,
                totp_login=use_totp_login,
            )
    else:
        if use_env_creds and not (ctx.phone and ctx.mpin):
            raise ValueError(
                "env_creds=True but PHONE_NO/MPIN not found. "
                "Place a .env file with PHONE_NO=\"...\" and MPIN=\"...\" "
                "in project root or examples/."
            )
        sdk = InitNubraSdk(
            env=env_map[env_key],
            env_creds=use_env_creds,
            totp_login=use_totp_login,
        )
    return MarketData(sdk)


def run_from_config(
    config: AnalyzerUIConfig,
    *,
    md_client: Any | None = None,
    prompt_parent: Any | None = None,
) -> dict[str, Any]:
    client = md_client or _create_market_data_client(
        env=config.env,
        use_env_creds=config.use_env_creds,
        use_totp_login=config.use_totp_login,
        prompt_parent=prompt_parent,
    )

    benchmark_symbol = config.benchmark_symbol.strip().upper() if config.benchmark_enabled else None
    common_kwargs = {
        "start": config.start.strip(),
        "end": config.end.strip(),
        "interval": config.interval.strip(),
        "benchmark_symbol": benchmark_symbol,
        "benchmark_exchange": config.benchmark_exchange.strip().upper(),
        "benchmark_instrument_type": config.benchmark_instrument_type.strip().upper(),
        "show_plots": config.show_plots,
        "save_plots": config.save_plots,
        "plots_dir": config.plots_dir.strip() or "nubrastats-plots",
        "generate_html": config.generate_html,
        "open_html": config.open_html,
        "html_output": config.html_output.strip() or None,
        "html_mode": config.html_mode.strip().lower() or "basic",
        "title": config.title.strip() or None,
        "display_metrics": config.display_metrics,
        "rf": float(config.risk_free_rate) / 100.0,
    }

    if config.portfolio_enabled:
        if not config.portfolio_items:
            raise ValueError("Portfolio mode is enabled, but no portfolio items were added")
        return nubra.analyze_portfolio(
            client,
            positions=config.portfolio_items,
            portfolio_name=config.portfolio_name.strip() or "Portfolio",
            **common_kwargs,
        )

    return nubra.analyze_symbol(
        client,
        symbol=config.symbol.strip().upper(),
        exchange=config.exchange.strip().upper(),
        instrument_type=config.instrument_type.strip().upper(),
        **common_kwargs,
    )


def launch_analyzer_ui(initial: AnalyzerUIConfig | None = None) -> None:
    import tkinter as tk
    from tkinter import messagebox, ttk

    try:
        from tkcalendar import DateEntry as CalendarDateEntry
    except Exception:
        CalendarDateEntry = None

    cfg = initial or AnalyzerUIConfig(start="2025-01-01", end=date.today().isoformat())

    root = tk.Tk()
    root.title("NubraStats Analyzer")
    root.geometry("1160x760")
    root.minsize(980, 640)
    root.resizable(True, True)
    try:
        root.state("zoomed")
    except Exception:
        # zoomed may not be available on all platforms/window managers.
        pass

    frame = ttk.Frame(root, padding=10)
    frame.pack(fill=tk.BOTH, expand=True)

    status_var = tk.StringVar(value="Fill details and click Generate Report.")

    env_var = tk.StringVar(value=cfg.env)
    env_creds_var = tk.BooleanVar(value=cfg.use_env_creds)
    totp_var = tk.BooleanVar(value=cfg.use_totp_login)

    symbol_var = tk.StringVar(value=cfg.symbol)
    exchange_var = tk.StringVar(value=cfg.exchange)
    instrument_var = tk.StringVar(value=cfg.instrument_type)
    portfolio_enabled_var = tk.BooleanVar(value=cfg.portfolio_enabled)
    portfolio_name_var = tk.StringVar(value=cfg.portfolio_name)
    portfolio_symbol_var = tk.StringVar(value="")
    portfolio_exchange_var = tk.StringVar(value="NSE")
    portfolio_type_var = tk.StringVar(value="STOCK")
    portfolio_qty_var = tk.StringVar(value="1")
    start_var = tk.StringVar(value=cfg.start)
    end_var = tk.StringVar(value=cfg.end)
    interval_var = tk.StringVar(value=cfg.interval)

    bench_enabled_var = tk.BooleanVar(value=cfg.benchmark_enabled)
    bench_symbol_var = tk.StringVar(value=cfg.benchmark_symbol)
    bench_exchange_var = tk.StringVar(value=cfg.benchmark_exchange)
    bench_type_var = tk.StringVar(value=cfg.benchmark_instrument_type)

    show_plots_var = tk.BooleanVar(value=cfg.show_plots)
    save_plots_var = tk.BooleanVar(value=cfg.save_plots)
    plots_dir_var = tk.StringVar(value=cfg.plots_dir)

    gen_html_var = tk.BooleanVar(value=cfg.generate_html)
    open_html_var = tk.BooleanVar(value=cfg.open_html)
    html_output_var = tk.StringVar(value=cfg.html_output)
    html_mode_var = tk.StringVar(value=cfg.html_mode)
    title_var = tk.StringVar(value=cfg.title)
    display_metrics_var = tk.BooleanVar(value=cfg.display_metrics)
    risk_free_rate_var = tk.StringVar(value=f"{cfg.risk_free_rate:g}")

    for upper_var in (
        symbol_var,
        exchange_var,
        instrument_var,
        portfolio_symbol_var,
        portfolio_exchange_var,
        portfolio_type_var,
        bench_symbol_var,
        bench_exchange_var,
        bench_type_var,
    ):
        _bind_uppercase_var(upper_var)

    ttk.Label(frame, text="NubraStats One-Click Analyzer", font=("Segoe UI", 13, "bold")).grid(
        row=0,
        column=0,
        columnspan=2,
        sticky="w",
        pady=(0, 8),
    )
    ttk.Label(
        frame,
        text="Landscape layout: inputs on left, run/report options on right.",
    ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))

    content = ttk.Frame(frame)
    content.grid(row=2, column=0, columnspan=2, sticky="nsew")
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(2, weight=1)

    left_wrap = ttk.Frame(content)
    left_canvas = tk.Canvas(left_wrap, highlightthickness=0)
    left_scroll = ttk.Scrollbar(left_wrap, orient="vertical", command=left_canvas.yview)
    left = ttk.Frame(left_canvas)

    left_canvas.configure(yscrollcommand=left_scroll.set)
    left_canvas.grid(row=0, column=0, sticky="nsew")
    left_scroll.grid(row=0, column=1, sticky="ns")
    left_wrap.columnconfigure(0, weight=1)
    left_wrap.rowconfigure(0, weight=1)

    left_window = left_canvas.create_window((0, 0), window=left, anchor="nw")

    def _refresh_left_scrollregion(_event=None) -> None:
        left_canvas.configure(scrollregion=left_canvas.bbox("all"))

    def _sync_left_width(event) -> None:
        left_canvas.itemconfigure(left_window, width=event.width)

    left.bind("<Configure>", _refresh_left_scrollregion)
    left_canvas.bind("<Configure>", _sync_left_width)

    def _on_mousewheel(event) -> None:
        if left_canvas.winfo_ismapped():
            left_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    left_canvas.bind_all("<MouseWheel>", _on_mousewheel)

    right = ttk.Frame(content)
    left_wrap.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
    right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
    content.columnconfigure(0, weight=1)
    content.columnconfigure(1, weight=1)
    content.rowconfigure(0, weight=1)

    # ---------------------------------------------------------------------
    # Left panel
    # ---------------------------------------------------------------------
    conn_box = ttk.LabelFrame(left, text="Connection", padding=10)
    conn_box.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    primary_box = ttk.LabelFrame(left, text="Primary Symbol", padding=10)
    primary_box.grid(row=1, column=0, sticky="ew", pady=(0, 8))
    portfolio_box = ttk.LabelFrame(left, text="Portfolio (Multiple Stocks)", padding=10)
    portfolio_box.grid(row=2, column=0, sticky="nsew", pady=(0, 8))
    bench_box = ttk.LabelFrame(left, text="Benchmark", padding=10)
    bench_box.grid(row=3, column=0, sticky="ew", pady=(0, 8))
    left.columnconfigure(0, weight=1)
    left.rowconfigure(2, weight=1)

    def add_entry(
        parent: ttk.Frame,
        label: str,
        var: tk.StringVar,
        row: int,
        width: int = 28,
    ) -> ttk.Entry:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        entry = ttk.Entry(parent, textvariable=var, width=width)
        entry.grid(row=row, column=1, sticky="w", pady=3)
        return entry

    def add_date_entry(
        parent: ttk.Frame,
        label: str,
        var: tk.StringVar,
        row: int,
        width: int = 18,
    ) -> tk.Widget:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        if CalendarDateEntry is not None:
            fallback = date.today() if "End Date" in label else date(2025, 1, 1)
            selected = _to_date_or_fallback(var.get(), fallback)
            picker = CalendarDateEntry(
                parent,
                textvariable=var,
                width=width,
                date_pattern="yyyy-mm-dd",
            )
            picker.grid(row=row, column=1, sticky="w", pady=3)
            picker.set_date(selected)
            var.set(selected.isoformat())
            return picker
        entry = ttk.Entry(parent, textvariable=var, width=width)
        entry.grid(row=row, column=1, sticky="w", pady=3)
        return entry

    conn_row = 0
    ttk.Label(conn_box, text="Environment").grid(row=conn_row, column=0, sticky="w", pady=3)
    env_combo = ttk.Combobox(
        conn_box,
        values=_ENV_NAMES,
        textvariable=env_var,
        width=10,
        state="readonly",
    )
    env_combo.grid(row=conn_row, column=1, sticky="w", pady=3)
    conn_row += 1
    ttk.Checkbutton(conn_box, text="Use .env credentials", variable=env_creds_var).grid(
        row=conn_row, column=0, columnspan=2, sticky="w", pady=2
    )
    conn_row += 1
    ttk.Checkbutton(conn_box, text="Use TOTP login", variable=totp_var).grid(
        row=conn_row, column=0, columnspan=2, sticky="w", pady=2
    )

    prim_row = 0
    primary_symbol_entry = add_entry(primary_box, "Symbol", symbol_var, prim_row, width=18)
    prim_row += 1
    primary_exchange_entry = add_entry(primary_box, "Exchange", exchange_var, prim_row, width=18)
    prim_row += 1
    ttk.Label(primary_box, text="Instrument Type").grid(row=prim_row, column=0, sticky="w", pady=3)
    primary_instrument_combo = ttk.Combobox(
        primary_box,
        values=_UI_INSTRUMENT_TYPES,
        textvariable=instrument_var,
        width=12,
        state="readonly",
    )
    primary_instrument_combo.grid(row=prim_row, column=1, sticky="w", pady=3)
    prim_row += 1
    add_date_entry(primary_box, "Start Date", start_var, prim_row, width=18)
    prim_row += 1
    add_date_entry(primary_box, "End Date", end_var, prim_row, width=18)
    prim_row += 1
    ttk.Label(primary_box, text="Interval").grid(row=prim_row, column=0, sticky="w", pady=3)
    interval_combo = ttk.Combobox(
        primary_box,
        values=_INTERVAL_ORDER,
        textvariable=interval_var,
        width=10,
        state="readonly",
    )
    interval_combo.grid(row=prim_row, column=1, sticky="w", pady=3)
    if CalendarDateEntry is None:
        ttk.Label(
            primary_box,
            text="Install date picker: pip install tkcalendar",
        ).grid(row=prim_row + 1, column=0, columnspan=2, sticky="w", pady=(6, 0))

    portfolio_positions: list[PortfolioItem] = []
    for item in cfg.portfolio_items:
        if isinstance(item, PortfolioItem):
            portfolio_positions.append(item)
            continue
        portfolio_positions.append(
            PortfolioItem(
                symbol=str(item.get("symbol", "")).strip().upper(),
                quantity=float(item.get("quantity", item.get("qty", 0))),
                exchange=str(item.get("exchange", "NSE")).strip().upper(),
                instrument_type=str(item.get("instrument_type", "STOCK")).strip().upper(),
            )
        )

    ttk.Checkbutton(
        portfolio_box,
        text="Enable Portfolio Mode (use multiple stocks + qty)",
        variable=portfolio_enabled_var,
    ).grid(row=0, column=0, columnspan=6, sticky="w", pady=(0, 4))

    ttk.Label(portfolio_box, text="Portfolio Name").grid(row=1, column=0, sticky="w", pady=2)
    ttk.Entry(portfolio_box, textvariable=portfolio_name_var, width=24).grid(
        row=1, column=1, columnspan=2, sticky="w", pady=2
    )

    portfolio_hint = ttk.Label(
        portfolio_box,
        text="Enable portfolio mode to add multiple stocks and quantities.",
    )
    portfolio_hint.grid(row=2, column=0, columnspan=6, sticky="w", pady=(2, 2))

    portfolio_editor = ttk.Frame(portfolio_box)
    portfolio_editor.grid(row=3, column=0, columnspan=6, sticky="nsew")
    portfolio_box.rowconfigure(3, weight=1)

    ttk.Label(portfolio_editor, text="Symbol").grid(row=0, column=0, sticky="w", pady=2)
    ttk.Entry(portfolio_editor, textvariable=portfolio_symbol_var, width=14).grid(
        row=0, column=1, sticky="w", pady=2
    )
    ttk.Label(portfolio_editor, text="Exchange").grid(row=0, column=2, sticky="w", pady=2)
    ttk.Entry(portfolio_editor, textvariable=portfolio_exchange_var, width=10).grid(
        row=0, column=3, sticky="w", pady=2
    )
    ttk.Label(portfolio_editor, text="Type").grid(row=0, column=4, sticky="w", pady=2)
    portfolio_type_combo = ttk.Combobox(
        portfolio_editor,
        values=_UI_INSTRUMENT_TYPES,
        textvariable=portfolio_type_var,
        width=10,
        state="readonly",
    )
    portfolio_type_combo.grid(row=0, column=5, sticky="w", pady=2)

    ttk.Label(portfolio_editor, text="Qty").grid(row=1, column=0, sticky="w", pady=2)
    ttk.Entry(portfolio_editor, textvariable=portfolio_qty_var, width=14).grid(
        row=1, column=1, sticky="w", pady=2
    )

    portfolio_tree = ttk.Treeview(
        portfolio_editor,
        columns=("symbol", "exchange", "itype", "qty"),
        show="headings",
        height=5,
    )
    portfolio_tree.heading("symbol", text="Symbol")
    portfolio_tree.heading("exchange", text="Exchange")
    portfolio_tree.heading("itype", text="Type")
    portfolio_tree.heading("qty", text="Qty")
    portfolio_tree.column("symbol", width=120, anchor="w")
    portfolio_tree.column("exchange", width=90, anchor="w")
    portfolio_tree.column("itype", width=90, anchor="w")
    portfolio_tree.column("qty", width=90, anchor="e")
    portfolio_tree.grid(row=2, column=0, columnspan=6, sticky="nsew", pady=(6, 2))
    portfolio_editor.rowconfigure(2, weight=1)
    for col in range(6):
        portfolio_editor.columnconfigure(col, weight=1 if col in {0, 1, 2, 3, 4} else 0)

    portfolio_btns = ttk.Frame(portfolio_editor)
    portfolio_btns.grid(row=3, column=0, columnspan=6, sticky="w", pady=(4, 0))

    def _refresh_portfolio_tree() -> None:
        for iid in portfolio_tree.get_children():
            portfolio_tree.delete(iid)
        for idx, pos in enumerate(portfolio_positions):
            portfolio_tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    pos.symbol,
                    pos.exchange,
                    pos.instrument_type,
                    f"{pos.quantity:g}",
                ),
            )

    def _add_portfolio_item() -> None:
        symbol = portfolio_symbol_var.get().strip().upper()
        exchange = portfolio_exchange_var.get().strip().upper() or "NSE"
        itype = portfolio_type_var.get().strip().upper() or "STOCK"
        try:
            qty = float(portfolio_qty_var.get().strip())
        except Exception:
            messagebox.showerror("NubraStats Error", "Quantity must be a valid number")
            return
        if not symbol:
            messagebox.showerror("NubraStats Error", "Portfolio symbol is required")
            return
        if qty <= 0:
            messagebox.showerror("NubraStats Error", "Quantity must be greater than 0")
            return
        key = (symbol, exchange, itype)
        if any((p.symbol, p.exchange, p.instrument_type) == key for p in portfolio_positions):
            messagebox.showerror("NubraStats Error", "Duplicate portfolio item is not allowed")
            return
        portfolio_positions.append(
            PortfolioItem(
                symbol=symbol,
                exchange=exchange,
                instrument_type=itype,
                quantity=qty,
            )
        )
        _refresh_portfolio_tree()
        portfolio_symbol_var.set("")
        portfolio_qty_var.set("1")

    def _remove_selected_portfolio_item() -> None:
        selected = portfolio_tree.selection()
        if not selected:
            return
        for iid in sorted((int(item) for item in selected), reverse=True):
            if 0 <= iid < len(portfolio_positions):
                portfolio_positions.pop(iid)
        _refresh_portfolio_tree()

    def _clear_portfolio_items() -> None:
        portfolio_positions.clear()
        _refresh_portfolio_tree()

    ttk.Button(portfolio_btns, text="+ Add", command=_add_portfolio_item).pack(side=tk.LEFT)
    ttk.Button(
        portfolio_btns,
        text="Remove Selected",
        command=_remove_selected_portfolio_item,
    ).pack(side=tk.LEFT, padx=(8, 0))
    ttk.Button(portfolio_btns, text="Clear", command=_clear_portfolio_items).pack(
        side=tk.LEFT, padx=(8, 0)
    )
    _refresh_portfolio_tree()

    bench_row = 0
    ttk.Checkbutton(bench_box, text="Enable Benchmark", variable=bench_enabled_var).grid(
        row=bench_row, column=0, columnspan=2, sticky="w", pady=2
    )
    bench_row += 1
    bench_symbol_entry = add_entry(
        bench_box,
        "Benchmark Symbol",
        bench_symbol_var,
        bench_row,
        width=18,
    )
    bench_row += 1
    bench_exchange_entry = add_entry(
        bench_box,
        "Benchmark Exchange",
        bench_exchange_var,
        bench_row,
        width=18,
    )
    bench_row += 1
    ttk.Label(bench_box, text="Benchmark Type").grid(row=bench_row, column=0, sticky="w", pady=3)
    bench_type_combo = ttk.Combobox(
        bench_box,
        values=_UI_INSTRUMENT_TYPES,
        textvariable=bench_type_var,
        width=12,
        state="readonly",
    )
    bench_type_combo.grid(row=bench_row, column=1, sticky="w", pady=3)

    # ---------------------------------------------------------------------
    # Right panel
    # ---------------------------------------------------------------------
    run_box = ttk.LabelFrame(right, text="Report & Run Options", padding=10)
    run_box.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
    right.columnconfigure(0, weight=1)

    run_row = 0
    ttk.Checkbutton(run_box, text="Show plots popup", variable=show_plots_var).grid(
        row=run_row, column=0, columnspan=2, sticky="w", pady=2
    )
    run_row += 1
    ttk.Checkbutton(run_box, text="Save plots (PNG)", variable=save_plots_var).grid(
        row=run_row, column=0, columnspan=2, sticky="w", pady=2
    )
    run_row += 1
    plot_entry = add_entry(run_box, "Plots Folder", plots_dir_var, run_row, width=34)
    run_row += 1

    ttk.Checkbutton(run_box, text="Generate HTML report", variable=gen_html_var).grid(
        row=run_row, column=0, columnspan=2, sticky="w", pady=2
    )
    run_row += 1
    open_html_check = ttk.Checkbutton(run_box, text="Open HTML report", variable=open_html_var)
    open_html_check.grid(row=run_row, column=0, columnspan=2, sticky="w", pady=2)
    run_row += 1
    ttk.Label(run_box, text="HTML Mode").grid(row=run_row, column=0, sticky="w", pady=3)
    html_mode_combo = ttk.Combobox(
        run_box,
        values=("basic", "detailed"),
        textvariable=html_mode_var,
        width=12,
        state="readonly",
    )
    html_mode_combo.grid(row=run_row, column=1, sticky="w", pady=3)
    run_row += 1
    html_entry = add_entry(run_box, "HTML Output File", html_output_var, run_row, width=34)
    run_row += 1
    add_entry(run_box, "Report Title", title_var, run_row, width=34)
    run_row += 1
    add_entry(run_box, "Risk-Free Rate (%)", risk_free_rate_var, run_row, width=12)
    run_row += 1
    ttk.Checkbutton(run_box, text="Display metrics in terminal", variable=display_metrics_var).grid(
        row=run_row, column=0, columnspan=2, sticky="w", pady=2
    )
    run_row += 1

    status_box = ttk.LabelFrame(right, text="Status", padding=10)
    status_box.grid(row=1, column=0, sticky="ew")
    ttk.Label(status_box, textvariable=status_var, foreground="#1f4f82", wraplength=420).grid(
        row=0,
        column=0,
        sticky="w",
        pady=(0, 8),
    )

    def _toggle_benchmark_state() -> None:
        if bench_enabled_var.get():
            bench_symbol_entry.configure(state="normal")
            bench_exchange_entry.configure(state="normal")
            bench_type_combo.configure(state="readonly")
        else:
            bench_symbol_entry.configure(state="disabled")
            bench_exchange_entry.configure(state="disabled")
            bench_type_combo.configure(state="disabled")

    def _toggle_output_state() -> None:
        if gen_html_var.get():
            html_entry.configure(state="normal")
            open_html_check.configure(state="normal")
            html_mode_combo.configure(state="readonly")
        else:
            html_entry.configure(state="disabled")
            open_html_check.configure(state="disabled")
            html_mode_combo.configure(state="disabled")
            open_html_var.set(False)

        if save_plots_var.get():
            plot_entry.configure(state="normal")
        else:
            plot_entry.configure(state="disabled")

    def _toggle_strategy_mode() -> None:
        if portfolio_enabled_var.get():
            primary_symbol_entry.configure(state="disabled")
            primary_exchange_entry.configure(state="disabled")
            primary_instrument_combo.configure(state="disabled")
            portfolio_editor.grid(row=3, column=0, columnspan=6, sticky="nsew")
            portfolio_hint.configure(
                text=(
                    "Portfolio mode enabled. Primary symbol fields are disabled; "
                    "date range still applies to portfolio analysis."
                )
            )
        else:
            primary_symbol_entry.configure(state="normal")
            primary_exchange_entry.configure(state="normal")
            primary_instrument_combo.configure(state="readonly")
            portfolio_editor.grid_forget()
            portfolio_hint.configure(
                text="Enable portfolio mode to add multiple stocks and quantities."
            )
        _refresh_left_scrollregion()

    bench_enabled_var.trace_add("write", lambda *_: _toggle_benchmark_state())
    save_plots_var.trace_add("write", lambda *_: _toggle_output_state())
    gen_html_var.trace_add("write", lambda *_: _toggle_output_state())
    portfolio_enabled_var.trace_add("write", lambda *_: _toggle_strategy_mode())
    _toggle_benchmark_state()
    _toggle_output_state()
    _toggle_strategy_mode()

    def _build_config() -> AnalyzerUIConfig:
        portfolio_enabled = portfolio_enabled_var.get()
        raw_title = title_var.get().strip()
        default_titles = {"Nubra UI Report", "Nubra Stock Analysis", "Nubra Portfolio Report"}
        resolved_title = raw_title
        if not raw_title or raw_title in default_titles:
            resolved_title = (
                "Nubra Portfolio Report" if portfolio_enabled else "Nubra Stock Analysis"
            )

        return AnalyzerUIConfig(
            env=env_var.get(),
            use_env_creds=env_creds_var.get(),
            use_totp_login=totp_var.get(),
            symbol=symbol_var.get(),
            exchange=exchange_var.get(),
            instrument_type=instrument_var.get(),
            portfolio_enabled=portfolio_enabled,
            portfolio_name=portfolio_name_var.get(),
            portfolio_items=[
                {
                    "symbol": p.symbol,
                    "exchange": p.exchange,
                    "instrument_type": p.instrument_type,
                    "quantity": float(p.quantity),
                }
                for p in portfolio_positions
            ],
            start=start_var.get(),
            end=end_var.get(),
            interval=interval_var.get(),
            benchmark_enabled=bench_enabled_var.get(),
            benchmark_symbol=bench_symbol_var.get(),
            benchmark_exchange=bench_exchange_var.get(),
            benchmark_instrument_type=bench_type_var.get(),
            show_plots=show_plots_var.get(),
            save_plots=save_plots_var.get(),
            plots_dir=plots_dir_var.get(),
            generate_html=gen_html_var.get(),
            open_html=open_html_var.get(),
            html_output=html_output_var.get(),
            html_mode=html_mode_var.get(),
            title=resolved_title,
            display_metrics=display_metrics_var.get(),
            risk_free_rate=float(risk_free_rate_var.get() or 6),
        )

    def on_generate() -> None:
        generate_btn.configure(state="disabled")
        status_var.set("Generating report...")
        root.update_idletasks()

        try:
            ui_cfg = _build_config()
            if ui_cfg.portfolio_enabled and not ui_cfg.portfolio_items:
                raise ValueError("Portfolio mode is enabled, but no portfolio items were added")
            run_cfg = replace(ui_cfg, show_plots=False)
            result = run_from_config(run_cfg, prompt_parent=root)
            lines = ["Analysis completed."]
            if ui_cfg.show_plots:
                label_hint = ui_cfg.portfolio_name if ui_cfg.portfolio_enabled else ui_cfg.symbol
                figures = _build_plot_figures(result, symbol=label_hint)
                if figures:
                    _open_plot_navigator(root, figures)
                    lines.append("Opened plot viewer (use Previous/Next or arrow keys).")
            if result.get("html_path"):
                lines.append(f"HTML: {result['html_path']}")
            if result.get("html_opened"):
                lines.append("HTML opened in browser.")
            if result.get("plot_paths"):
                lines.append(f"Saved PNG files: {len(result['plot_paths'])}")
            status_var.set("Done.")
            messagebox.showinfo("NubraStats", "\n".join(lines))
        except Exception as exc:
            status_var.set("Failed.")
            messagebox.showerror("NubraStats Error", _friendly_error_message(exc))
        finally:
            generate_btn.configure(state="normal")

    btn_frame = ttk.Frame(status_box)
    btn_frame.grid(row=1, column=0, sticky="w", pady=4)
    generate_btn = ttk.Button(btn_frame, text="Generate Report", command=on_generate)
    generate_btn.pack(side=tk.LEFT, padx=(0, 8))
    ttk.Button(btn_frame, text="Close", command=root.destroy).pack(side=tk.LEFT)

    root.mainloop()
