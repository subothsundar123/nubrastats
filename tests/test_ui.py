from __future__ import annotations

import os

from nubrastats import ui


def test_run_from_config_passes_normalized_values(monkeypatch) -> None:
    captured: dict = {}

    def _fake_analyze(md_client, **kwargs):
        captured["md_client"] = md_client
        captured["kwargs"] = kwargs
        return {"ok": True}

    fake_client = object()
    monkeypatch.setattr(ui.nubra, "analyze_symbol", _fake_analyze)

    cfg = ui.AnalyzerUIConfig(
        symbol="reliance",
        exchange="nse",
        instrument_type="stock",
        start="2025-01-01",
        end="2025-01-31",
        interval="1d",
        benchmark_enabled=False,
        benchmark_symbol="nifty",
        show_plots=True,
        save_plots=False,
        generate_html=True,
        open_html=True,
    )
    result = ui.run_from_config(cfg, md_client=fake_client)

    assert result == {"ok": True}
    assert captured["md_client"] is fake_client
    assert captured["kwargs"]["symbol"] == "RELIANCE"
    assert captured["kwargs"]["exchange"] == "NSE"
    assert captured["kwargs"]["instrument_type"] == "STOCK"
    assert captured["kwargs"]["benchmark_symbol"] is None
    assert captured["kwargs"]["generate_html"] is True
    assert captured["kwargs"]["open_html"] is True


def test_run_from_config_builds_client_when_missing(monkeypatch) -> None:
    fake_client = object()
    created: dict = {}

    def _fake_create_market_data_client(**kwargs):
        created.update(kwargs)
        return fake_client

    called: dict = {}

    def _fake_analyze(md_client, **kwargs):
        called["md_client"] = md_client
        called["kwargs"] = kwargs
        return {"ok": True}

    monkeypatch.setattr(ui, "_create_market_data_client", _fake_create_market_data_client)
    monkeypatch.setattr(ui.nubra, "analyze_symbol", _fake_analyze)

    cfg = ui.AnalyzerUIConfig(env="PROD", use_env_creds=False, use_totp_login=True)
    ui.run_from_config(cfg)

    assert created == {"env": "PROD", "use_env_creds": False, "use_totp_login": True}
    assert called["md_client"] is fake_client


def test_run_from_config_portfolio_mode_calls_analyze_portfolio(monkeypatch) -> None:
    captured: dict = {}
    fake_client = object()

    def _fake_portfolio(md_client, **kwargs):
        captured["md_client"] = md_client
        captured["kwargs"] = kwargs
        return {"ok": True}

    monkeypatch.setattr(ui.nubra, "analyze_portfolio", _fake_portfolio)
    monkeypatch.setattr(ui.nubra, "analyze_symbol", lambda *_args, **_kwargs: {"wrong": True})

    cfg = ui.AnalyzerUIConfig(
        portfolio_enabled=True,
        portfolio_name="core",
        portfolio_items=[
            {"symbol": "reliance", "exchange": "nse", "instrument_type": "stock", "quantity": 10},
            {"symbol": "tcs", "exchange": "nse", "instrument_type": "stock", "quantity": 5},
        ],
        benchmark_enabled=False,
    )
    result = ui.run_from_config(cfg, md_client=fake_client)

    assert result == {"ok": True}
    assert captured["md_client"] is fake_client
    assert captured["kwargs"]["portfolio_name"] == "core"
    assert len(captured["kwargs"]["positions"]) == 2
    assert captured["kwargs"]["benchmark_symbol"] is None


def test_load_env_file_handles_spaces_and_quotes(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        'PHONE_NO= "9999999999"\nMPIN= "1234"\nexport TOKEN = "abc"\n',
        encoding="utf-8",
    )
    monkeypatch.delenv("PHONE_NO", raising=False)
    monkeypatch.delenv("MPIN", raising=False)
    monkeypatch.delenv("TOKEN", raising=False)

    loaded = ui._load_env_file(env_path)

    assert loaded == 3
    assert os.environ["PHONE_NO"] == "9999999999"
    assert os.environ["MPIN"] == "1234"
    assert os.environ["TOKEN"] == "abc"


def test_seed_env_aliases_sets_lowercase_and_uppercase(monkeypatch) -> None:
    monkeypatch.setenv("PHONE_NO", "9876543210")
    monkeypatch.setenv("MPIN", "5678")
    monkeypatch.delenv("phone", raising=False)

    ui._seed_env_aliases()

    assert os.environ["PHONE_NO"] == "9876543210"
    assert os.environ["phone"] == "9876543210"
    assert os.environ["MPIN"] == "5678"
    assert os.environ["mpin"] == "5678"
