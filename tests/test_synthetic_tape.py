"""Offline tests for the simulated-tape robustness layer (loki_v8.synthetic).

Everything here is deterministic: fixtures are generated from a seeded RNG, so
bar shapes, fingerprints and pass/fail verdicts are reproducible. No network,
no disk, no wall clock.
"""

import numpy as np
import pandas as pd
import pytest

from loki_v8 import synthetic as syn
from loki_v8.config import LokiConfig


def synthetic_bars(n=520, seed=7, freq="D"):
    """A seeded random-walk OHLCV frame with honest bar geometry."""
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.0004, 0.022, n)
    close = 100.0 * np.exp(np.cumsum(steps))
    open_ = np.concatenate(([100.0], close[:-1]))
    high = np.maximum(open_, close) * (1.0 + np.abs(rng.normal(0, 0.007, n)))
    low = np.minimum(open_, close) * (1.0 - np.abs(rng.normal(0, 0.007, n)))
    volume = rng.integers(1_000, 9_000, n).astype(float)
    index = pd.date_range("2019-01-01", periods=n, freq=freq)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=index,
    )


def base_cfg():
    return LokiConfig(period="2y", lookback_bars=60, signal_threshold=10.0)


PARAMS = {"signal_threshold": 10.0, "stop_loss_atr": 3.0, "take_profit_atr": 2.0}


class TestBlockBootstrap:
    def test_preserves_shape_and_geometry(self):
        source = synthetic_bars(600)
        tape = syn.block_bootstrap(source, 400, seed=11)

        assert len(tape) == 400
        assert list(tape.columns) == list(syn.OHLCV_COLUMNS)
        assert tape.index.is_monotonic_increasing
        body_high = tape[["open", "close"]].max(axis=1)
        body_low = tape[["open", "close"]].min(axis=1)
        assert (tape["high"] >= body_high - 1e-9).all()
        assert (tape["low"] <= body_low + 1e-9).all()
        assert (tape["low"] > 0).all()
        assert (tape["volume"] >= 0).all()

    def test_keeps_the_source_return_distribution(self):
        source = synthetic_bars(800, seed=3)
        tape = syn.block_bootstrap(source, 800, seed=5)
        source_sigma = float(np.log(source["close"]).diff().std())
        tape_sigma = float(np.log(tape["close"]).diff().std())
        # Same order of magnitude, not the same path: bootstrap reshuffles
        # blocks but must not blow up or flatten volatility.
        assert 0.6 * source_sigma < tape_sigma < 1.4 * source_sigma

    def test_deterministic_per_seed(self):
        source = synthetic_bars(500)
        first = syn.block_bootstrap(source, 300, seed=11)
        again = syn.block_bootstrap(source, 300, seed=11)
        other = syn.block_bootstrap(source, 300, seed=12)

        assert first.equals(again)
        assert not first.equals(other)
        assert syn.tape_fingerprint(first) == syn.tape_fingerprint(again)
        assert syn.tape_fingerprint(first) != syn.tape_fingerprint(other)

    def test_anchor_price(self):
        source = synthetic_bars(500)
        tape = syn.block_bootstrap(source, 120, seed=2, anchor_price=42.5)
        assert tape["close"].iloc[0] == pytest.approx(42.5)
        assert tape["open"].iloc[0] == pytest.approx(42.5)

    def test_rejects_short_input(self):
        with pytest.raises(ValueError):
            syn.block_bootstrap(synthetic_bars(10), 100)

    def test_rejects_bad_length(self):
        with pytest.raises(ValueError):
            syn.block_bootstrap(synthetic_bars(200), 1)

    def test_rejects_missing_columns(self):
        broken = synthetic_bars(200).drop(columns=["volume"])
        with pytest.raises(ValueError):
            syn.block_bootstrap(broken, 100)

    def test_synthetic_tapes_are_distinct(self):
        source = synthetic_bars(400)
        tapes = syn.synthetic_tapes(source, count=3, bars=200)
        fingerprints = {syn.tape_fingerprint(tape) for tape in tapes}
        assert len(tapes) == 3
        assert len(fingerprints) == 3


class TestWindowValidation:
    def test_reports_one_entry_per_window(self):
        result = syn.validate_windows(
            synthetic_bars(900), PARAMS, base_cfg(), "TEST", 365, windows=(1, 2)
        )
        assert [w["label"] for w in result["windows"]] == ["1y", "2y"]
        assert isinstance(result["passes"], bool)
        for entry in result["windows"]:
            assert set(entry) >= {"label", "bars", "metrics", "passes", "reasons"}
            assert entry["passes"] is (not entry["reasons"])

    def test_short_slice_is_a_failed_check_not_an_exception(self):
        result = syn.validate_windows(
            synthetic_bars(500), PARAMS, base_cfg(), "TEST", 365, windows=(1,)
        )
        entry = result["windows"][0]
        # 365 bars is below MIN_TAPE_BARS, so it must be reported as skipped.
        assert entry["passes"] is False
        assert any("insufficient history" in reason for reason in entry["reasons"])
        assert result["passes"] is False


class TestSyntheticValidation:
    def test_structure_and_pooled_metrics(self):
        result = syn.validate_synthetic(
            synthetic_bars(700),
            PARAMS,
            base_cfg(),
            "TEST",
            365,
            seeds=(11, 23),
            bars=420,
        )
        assert [t["seed"] for t in result["tapes"]] == [11, 23]
        assert result["bars"] == 420
        assert result["block_size"] == syn.DEFAULT_BLOCK_SIZE
        assert set(result["pooled"]) == {
            "trades",
            "return_pct",
            "win_rate_pct",
            "profit_factor",
            "max_drawdown_pct",
        }
        assert result["passes"] is (not result["reasons"])
        assert result["thresholds"]["min_trades"] == syn.SYNTHETIC_MIN_TRADES

    def test_deterministic_verdict(self):
        source = synthetic_bars(700, seed=9)
        first = syn.validate_synthetic(source, PARAMS, base_cfg(), "TEST", 365, seeds=(11,), bars=420)
        again = syn.validate_synthetic(source, PARAMS, base_cfg(), "TEST", 365, seeds=(11,), bars=420)
        assert first["passes"] == again["passes"]
        assert first["pooled"] == again["pooled"]
        assert first["source_fingerprint"] == again["source_fingerprint"]
        assert first["tapes"][0]["fingerprint"] == again["tapes"][0]["fingerprint"]

    def test_zero_fill_tape_is_unpowered_not_a_failed_edge(self):
        # A threshold nothing can reach produces no trades at all. The tapes
        # learned nothing about the edge, so the reason must be filed as
        # missing evidence rather than as a losing result.
        never_fires = {"signal_threshold": 999.0, "stop_loss_atr": 3.0, "take_profit_atr": 2.0}
        result = syn.validate_synthetic(
            synthetic_bars(700), never_fires, base_cfg(), "TEST", 365, seeds=(11, 23), bars=420
        )
        assert result["passes"] is False
        assert result["powered"] is False
        assert result["evidence_reasons"]
        assert all("pooled trades" in r for r in result["evidence_reasons"])

    def test_powered_true_when_the_floor_was_reached(self):
        result = syn.validate_synthetic(
            synthetic_bars(700), PARAMS, base_cfg(), "TEST", 365, seeds=(11, 23), bars=420
        )
        # `powered` describes whether the sample could be judged, not whether
        # it won: it tracks the trade floor alone.
        assert result["powered"] is (result["pooled"]["trades"] >= syn.SYNTHETIC_MIN_TRADES)


class TestSummary:
    def test_summarises_both_checks(self):
        window = {"passes": False, "windows": [{"label": "5y", "passes": False}]}
        synthetic = {"passes": True, "pooled": {"profit_factor": 1.9}, "profitable_share": 1.0}
        line = syn.summarise(window, synthetic)
        assert "windows fail" in line
        assert "sim ok" in line

    def test_empty_input_gives_empty_line(self):
        assert syn.summarise(None, None) == ""


class TestGateVerdict:
    def test_all_three_must_agree(self):
        from loki_v8.train_crypto import gate_verdict

        window = {"passes": True, "windows": [{"label": "5y", "passes": True}]}
        synthetic = {"passes": True, "pooled": {"profit_factor": 1.4}, "profitable_share": 1.0}

        assert gate_verdict(True, window, synthetic)["good"] is True
        assert gate_verdict(False, window, synthetic)["good"] is False
        assert gate_verdict(True, {"passes": False, "windows": []}, synthetic)["good"] is False
        assert gate_verdict(True, window, {"passes": False, "reasons": ["x"]})["good"] is False

    def test_missing_check_is_not_a_pass(self):
        from loki_v8.train_crypto import gate_verdict

        verdict = gate_verdict(True, None, None)
        assert verdict["good"] is False
        assert verdict["windows"] is False
        assert verdict["synthetic"] is False
        assert verdict["verdict"] == "research only"

    def test_verified_verdict_shape(self):
        from loki_v8.train_crypto import gate_verdict

        verdict = gate_verdict(
            True,
            {"passes": True, "windows": [{"label": "5y", "passes": True}]},
            {"passes": True, "pooled": {"profit_factor": 2.0}, "profitable_share": 1.0},
        )
        assert verdict["verdict"] == "verified"
        assert {
            "hurdles",
            "windows",
            "synthetic",
            "synthetic_powered",
            "good",
            "verdict",
            "detail",
        } == set(verdict)

    def test_thin_sample_reads_as_untested_not_failed(self):
        """A tape set that never reached the fill floor did not disprove anything."""
        from loki_v8.train_crypto import gate_verdict

        thin = {
            "passes": False,
            "powered": False,
            "reasons": ["pooled trades 6 < 10"],
            "evidence_reasons": ["pooled trades 6 < 10"],
            "edge_reasons": [],
            "pooled": {"trades": 6, "profit_factor": 0.0, "return_pct": 0.0},
            "profitable_share": 0.0,
        }
        verdict = gate_verdict(True, {"passes": True, "windows": []}, thin)
        # Still not promotable — thin evidence is never a pass.
        assert verdict["good"] is False
        assert verdict["verdict"] == "untested"
        assert verdict["synthetic_powered"] is False

    def test_a_failed_edge_stays_research_only(self):
        from loki_v8.train_crypto import gate_verdict

        losing = {
            "passes": False,
            "powered": True,
            "reasons": ["pooled profit factor 0.88 < 1.05"],
            "evidence_reasons": [],
            "edge_reasons": ["pooled profit factor 0.88 < 1.05"],
            "pooled": {"trades": 32, "profit_factor": 0.88, "return_pct": -0.83},
            "profitable_share": 0.33,
        }
        verdict = gate_verdict(True, {"passes": True, "windows": []}, losing)
        assert verdict["good"] is False
        assert verdict["verdict"] == "research only"
        assert verdict["synthetic_powered"] is True

    def test_untested_never_outscores_a_verified_profile(self):
        from loki_v8.train_crypto import gate_verdict

        thin = gate_verdict(
            True,
            {"passes": True, "windows": []},
            {"passes": False, "powered": False, "reasons": ["pooled trades 4 < 10"], "pooled": {}},
        )
        assert thin["good"] is False

    def test_summary_says_untested_for_thin_tapes(self):
        thin = {
            "passes": False,
            "powered": False,
            "evidence_reasons": ["pooled trades 6 < 10"],
            "reasons": ["pooled trades 6 < 10", "pooled profit factor 0.0 < 1.05"],
            "pooled": {"trades": 6, "profit_factor": 0.0},
            "profitable_share": 0.0,
        }
        line = syn.summarise(None, thin)
        assert "sim untested" in line
        assert "sim fail" not in line
