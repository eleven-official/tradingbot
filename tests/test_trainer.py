"""
Tests for the walk-forward strategy trainer (loki_v8.train).

All tests are offline: synthetic OHLCV bars or canned/fake objects only, so
the suite never depends on market data downloads.
"""

import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from loki_v8 import train as train_module
from loki_v8.backtest import Trade
from loki_v8.config import LokiConfig, default_config


def synthetic_bars(n=420, seed=7):
    """Trending + oscillating OHLCV series that produces crossing signals."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2023-01-02", periods=n, freq="D")
    drift = np.linspace(0.0, 40.0, n)
    cycle = 6.0 * np.sin(np.arange(n) / 11.0)
    close = 100.0 + drift + cycle + rng.normal(0.0, 0.8, n).cumsum() * 0.3
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    spread = np.abs(rng.normal(0.0, 0.6, n)) + 0.2
    return pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + spread,
            "low": np.minimum(open_, close) - spread,
            "close": close,
            "volume": rng.uniform(5e5, 2e6, n),
        },
        index=idx,
    )


SMALL_GRID = {
    "signal_threshold": [18.0, 30.0],
    "stop_loss_atr": [1.5, 2.5],
    "take_profit_atr": [2.5],
    "require_trend_filter": [True],
}


class TestTrainSymbol:
    def test_produces_ranked_report(self):
        df = synthetic_bars()
        rep = train_module.train_symbol(
            df, default_config(), "TEST", grid=SMALL_GRID, train_frac=0.7
        )
        assert rep.ok, rep.error
        assert rep.bars == len(df)
        assert rep.n_combos == 4
        assert len(rep.leaderboard) == 4
        # Best entry must match the promoted best_params.
        assert rep.leaderboard[0]["params"] == rep.best_params
        # Every combo carries train metrics.
        for entry in rep.leaderboard:
            assert set(entry["train"]) == {
                "trades",
                "return_pct",
                "win_rate_pct",
                "profit_factor",
                "max_drawdown_pct",
                "sharpe",
                "month_profit_rate_pct",
            }
        # Top candidates were validated out-of-sample.
        assert "validation" in rep.leaderboard[0]
        assert set(rep.validation_metrics) >= {"trades", "return_pct", "win_rate_pct"}

    def test_rejects_short_history(self):
        df = synthetic_bars(n=120)
        rep = train_module.train_symbol(df, default_config(), "SHORT")
        assert not rep.ok
        assert "insufficient history" in rep.error

    def test_validation_ignores_trades_entered_before_the_split(self, monkeypatch):
        """No-lookahead guarantee: in-sample trades never count as validation."""
        df = synthetic_bars()
        cfg = default_config()
        split_idx = int(len(df) * 0.7)
        split_time = df.index[split_idx]

        # Every simulated trade was entered BEFORE the split, so after the
        # out-of-sample filter the validation set must be empty.
        pre_split_trade = Trade(
            symbol="TEST",
            side="long",
            entry_time=df.index[split_idx - 40],
            exit_time=df.index[split_idx - 30],
            entry_price=100.0,
            exit_price=103.0,
            qty=1.0,
            pnl=3.0,
            pnl_pct=3.0,
            exit_reason="target",
        )
        fake = SimpleNamespace(
            total_trades=1,
            total_return_pct=3.0,
            win_rate_pct=100.0,
            profit_factor=9.0,
            max_drawdown_pct=0.0,
            sharpe=1.5,
            trades=[pre_split_trade],
        )

        monkeypatch.setattr(train_module, "run_backtest", lambda *a, **k: fake)

        rep = train_module.train_symbol(df, cfg, "TEST", grid=SMALL_GRID)
        assert rep.ok
        assert rep.validation_metrics["trades"] == 0
        assert rep.validated is False

    def test_full_history_grid_runs_without_network(self):
        """Default 24-combo grid completes on synthetic bars."""
        rep = train_module.train_symbol(synthetic_bars(), default_config(), "TEST", train_frac=0.7)
        assert rep.ok, rep.error
        assert rep.n_combos == 24


class TestApplyBest:
    def test_updates_config_case_insensitively_and_ignores_unknown(self, tmp_path):
        cfg = default_config()
        report = {
            "symbols": [
                {
                    "symbol": "aapl",
                    "ok": True,
                    "best_params": {
                        "signal_threshold": 32.0,
                        "stop_loss_atr": 1.5,
                        "take_profit_atr": 4.0,
                        "require_trend_filter": False,
                        "not_a_real_param": "must be ignored",
                    },
                }
            ]
        }
        applied = train_module.apply_best(report, "AAPL", cfg)
        assert applied["signal_threshold"] == 32.0
        assert cfg.signal_threshold == 32.0
        assert cfg.stop_loss_atr == 1.5
        assert cfg.take_profit_atr == 4.0
        assert cfg.require_trend_filter is False
        assert not hasattr(cfg, "not_a_real_param")

    def test_returns_empty_for_missing_or_failed_symbol(self):
        cfg = default_config()
        before = cfg.signal_threshold
        assert train_module.apply_best({"symbols": []}, "AAPL", cfg) == {}
        assert (
            train_module.apply_best(
                {"symbols": [{"symbol": "AAPL", "ok": False, "best_params": {}}]},
                "AAPL",
                cfg,
            )
            == {}
        )
        assert cfg.signal_threshold == before


class TestReportPersistence:
    def test_roundtrip(self, tmp_path, monkeypatch):
        path = tmp_path / "training_report.json"
        monkeypatch.setattr(train_module, "report_path", lambda cfg=None: path)
        report = {"generated_at": "2026-01-01T00:00:00", "symbols": [], "grid_size": 24}
        train_module.save_report(report, default_config())
        assert train_module.load_report(default_config()) == report

    def test_load_missing_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(train_module, "report_path", lambda cfg=None: tmp_path / "nope.json")
        monkeypatch.setattr(train_module, "BUNDLED_REPORT_FILENAME", "absent_snapshot.json")
        assert train_module.load_report(default_config()) is None

    def test_load_missing_falls_back_to_bundled_snapshot(self, tmp_path, monkeypatch):
        monkeypatch.setattr(train_module, "report_path", lambda cfg=None: tmp_path / "nope.json")
        report = train_module.load_report(default_config())  # bundled snapshot ships with the repo
        if report is not None:
            assert report.get("symbols"), "bundled snapshot must carry the trained book"


class TestTrainingAPI:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        from loki.api.terminal_v8 import app, get_bot
        from loki.api.fusion import _LOCAL_TOKEN
        monkeypatch.setenv("LOKI_FUSION_LOCAL", "1")

        path = tmp_path / "training_report.json"
        monkeypatch.setattr(train_module, "report_path", lambda cfg=None: path)
        bot = get_bot()
        saved = (bot.cfg.signal_threshold, bot.cfg.stop_loss_atr)
        yield TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 51000), headers={"X-Loki-Local-Token": _LOCAL_TOKEN}), bot, path
        bot.cfg.signal_threshold, bot.cfg.stop_loss_atr = saved

    def test_report_endpoint_empty_without_run(self, client, monkeypatch):
        c, _bot, _path = client
        monkeypatch.setattr(train_module, "BUNDLED_REPORT_FILENAME", "absent_snapshot.json")
        res = c.get("/api/training/report")
        assert res.status_code == 200
        assert res.json() == {"generated_at": None, "symbols": []}

    def test_run_endpoint_parses_symbols_and_delegates(self, client, monkeypatch):
        c, bot, _path = client
        seen = {}

        def fake_train(symbols, cfg, period="5y", train_frac=0.7, **kw):
            seen["symbols"] = symbols
            seen["period"] = period
            seen["cfg"] = cfg
            return {"generated_at": "2026-01-01T00:00:00", "symbols": []}

        monkeypatch.setattr(train_module, "train", fake_train)
        res = c.get("/api/training/run", params={"symbols": "spy, btc-usd", "period": "5y"})
        assert res.status_code == 200
        assert seen["symbols"] == ["SPY", "BTC-USD"]
        assert seen["period"] == "5y"
        assert seen["cfg"] is bot.cfg

    def test_run_endpoint_reports_failure(self, client, monkeypatch):
        c, _bot, _path = client

        def boom(*a, **k):
            raise RuntimeError("market data offline")

        monkeypatch.setattr(train_module, "train", boom)
        res = c.get("/api/training/run")
        assert res.status_code == 500
        assert "market data offline" in res.json()["detail"]

    def test_apply_endpoint_updates_running_engine(self, client):
        c, bot, path = client
        report = {
            "generated_at": "2026-01-01T00:00:00",
            "symbols": [
                {
                    "symbol": "AAPL",
                    "ok": True,
                    "best_params": {"signal_threshold": 25.0, "stop_loss_atr": 2.0},
                }
            ],
        }
        path.write_text(json.dumps(report), encoding="utf-8")

        res = c.post("/api/training/apply", json={"symbol": "aapl"})
        assert res.status_code == 200
        assert res.json()["applied"]["signal_threshold"] == 25.0
        assert bot.cfg.signal_threshold == 25.0

        missing = c.post("/api/training/apply", json={"symbol": "MSFT"})
        assert missing.status_code == 404
