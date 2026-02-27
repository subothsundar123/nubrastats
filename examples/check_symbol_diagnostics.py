from __future__ import annotations

import os
import platform
import sys
import traceback
from pathlib import Path
from typing import Any

import nubrastats as ns

# ============================================================================
# USER SETTINGS (edit these values)
# ============================================================================
ENV_NAME = "UAT"  # UAT | PROD | DEV | STAGING
USE_ENV_CREDS = True
USE_TOTP_LOGIN = False
ENV_FILE = Path(__file__).resolve().parent / ".env"  # e.g. examples/.env

SYMBOL = "HAL"
EXCHANGE = "NSE"
INSTRUMENT_TYPE = "STOCK"  # STOCK | INDEX | OPT | FUT
START = "2025-01-01"
END = "2025-12-31"
INTERVAL = "1d"  # 1s,1m,2m,3m,5m,15m,30m,1h,1d,1w,1mt
# ============================================================================


def _line() -> None:
    print("=" * 88)


def _safe_stdout_utf8() -> None:
    # Avoid Windows console encoding failures during SDK prompts/logs.
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass


def _load_env_file(path: Path) -> int:
    if not path.exists():
        return 0
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


def _mk_client() -> Any:
    from nubra_python_sdk.marketdata.market_data import MarketData
    from nubra_python_sdk.start_sdk import InitNubraSdk, NubraEnv

    env_map = {
        "UAT": NubraEnv.UAT,
        "PROD": NubraEnv.PROD,
        "DEV": NubraEnv.DEV,
        "STAGING": NubraEnv.STAGING,
    }
    env_key = ENV_NAME.strip().upper()
    if env_key not in env_map:
        raise ValueError(f"Invalid ENV_NAME: {ENV_NAME}. Use one of {sorted(env_map.keys())}")

    sdk = InitNubraSdk(
        env=env_map[env_key],
        env_creds=USE_ENV_CREDS,
        totp_login=USE_TOTP_LOGIN,
    )
    return MarketData(sdk)


def main() -> None:
    _safe_stdout_utf8()

    _line()
    print("Nubra Symbol Diagnostics")
    print(f"Python      : {sys.version.split()[0]} ({platform.system()})")
    print(f"CWD         : {Path.cwd()}")
    print(f"nubrastats  : {ns.__file__}")
    print(f"ENV         : {ENV_NAME} | env_creds={USE_ENV_CREDS} | totp={USE_TOTP_LOGIN}")
    print(f"Symbol Req  : {SYMBOL} [{EXCHANGE}/{INSTRUMENT_TYPE}] {INTERVAL} {START} -> {END}")

    _line()
    print("Step 1: Load credentials")
    loaded = _load_env_file(ENV_FILE)
    _seed_env_aliases()
    phone = os.environ.get("PHONE_NO", "")
    mpin = os.environ.get("MPIN", "")
    print(f".env path   : {ENV_FILE} (exists={ENV_FILE.exists()})")
    print(f"keys loaded : {loaded}")
    print(f"PHONE_NO set: {bool(phone)} (len={len(phone)})")
    print(f"MPIN set    : {bool(mpin)} (len={len(mpin)})")

    _line()
    print("Step 2: Init SDK client (OTP prompt may appear)")
    try:
        md_client = _mk_client()
        print("SDK init    : OK")
    except Exception as exc:
        print(f"SDK init    : FAIL -> {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return

    _line()
    print("Step 3: Build payload")
    try:
        payload = ns.nubra.build_historical_payload(
            symbol=SYMBOL,
            exchange=EXCHANGE,
            instrument_type=INSTRUMENT_TYPE,
            start=START,
            end=END,
            interval=INTERVAL,
            fields=["close"],
        )
        print("Payload     :", payload)
    except Exception as exc:
        print(f"Payload      FAIL -> {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return

    _line()
    print("Step 4: Raw API call")
    try:
        response = md_client.historical_data(payload)
        msg = getattr(response, "message", "")
        result_len = len(getattr(response, "result", []) or [])
        print(f"API message : {msg!r}")
        print(f"result blocks: {result_len}")
    except Exception as exc:
        print(f"API call    : FAIL -> {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return

    _line()
    print("Step 5: Parse close series")
    try:
        parsed = ns.nubra.close_series_from_historical_response(response, symbol=SYMBOL)
        print(f"parsed rows : {len(parsed)}")
        if not parsed.empty:
            print(f"parsed first: {parsed.index.min()} -> {float(parsed.iloc[0]):.4f}")
            print(f"parsed last : {parsed.index.max()} -> {float(parsed.iloc[-1]):.4f}")
    except Exception as exc:
        print(f"Parse       : FAIL -> {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return

    _line()
    print("Step 6: High-level fetch_close_series")
    try:
        series = ns.nubra.fetch_close_series(
            md_client=md_client,
            symbol=SYMBOL,
            exchange=EXCHANGE,
            instrument_type=INSTRUMENT_TYPE,
            start=START,
            end=END,
            interval=INTERVAL,
        )
        print(f"fetch rows  : {len(series)}")
        print(f"fetch first : {series.index.min()} -> {float(series.iloc[0]):.4f}")
        print(f"fetch last  : {series.index.max()} -> {float(series.iloc[-1]):.4f}")
    except Exception as exc:
        print(f"fetch_close : FAIL -> {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return

    _line()
    print("Done: Symbol data is available and parsed.")


if __name__ == "__main__":
    main()
