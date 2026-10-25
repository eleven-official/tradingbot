"""AI paper-trading endpoint: review-only pipeline, paper fills in browser.

Two contracts carry the honesty guarantees here:

1. ``/step`` builds a FRESH risk agent per request aligned with the
   caller's browser paper ledger (day baseline + loss streak). The cached
   pipeline is shared between every caller, so its own risk manager is
   never mutated — that would leak one browser's state into another's.
2. ``/bars`` serves the engine's cached history as completed candles,
   newest LAST, skipping malformed rows instead of inventing them.
"""

import pandas as pd
from fastapi.testclient import TestClient

from loki.api import ai_paper
from loki.api.server import app
from loki_v8.config import LokiConfig

client = TestClient(app)


class FakeRiskManager:
    def __init__(self):
        self.day_start_equity = 100000.0
        self._consecutive_losses = 0
        self.resets = []

    def reset_day(self, equity):
        self.resets.append(equity)
        self.day_start_equity = equity
        self._consecutive_losses = 0


class FakeRiskAgent:
    def __init__(self):
        self.risk = FakeRiskManager()

    def run(self, posture, signal, equity, open_positions, price):
        if signal is None:
            return {"approved": False, "reason": "no_signal"}
        if equity < 1000:
            return {"approved": False, "reason": "insufficient_equity"}
        return {"approved": True, "reason": "ok", "action": signal["action"], "qty": 37.0}


class FakePipeline:
    def __init__(self, risk=None, provider=None):
        self.risk = risk if risk is not None else FakeRiskAgent()
        self.provider = provider


ANALYSIS = {
    "price": 512.4,
    "trained_profile_applied": True,
    "regime": "BULL",
    "director": {"posture": "long", "thesis": "SPY: strong uptrend (trend_score=+78)"},
    "quant": {
        "action": "BUY",
        "score": 1.2,
        "confidence": 61.0,
        "entry": 512.4,
        "stop": 498.0,
        "target": 533.0,
        "reasons": ["trend alignment"],
    },
}


def _stub(monkeypatch):
    monkeypatch.setattr(ai_paper, "_analyze", lambda symbol: dict(ANALYSIS))
    monkeypatch.setattr(
        ai_paper, "_get_pipeline", lambda symbol: (FakePipeline(), LokiConfig(), True)
    )


class TestAiStep:
    def test_step_returns_full_trail(self, monkeypatch):
        _stub(monkeypatch)
        response = client.post(
            "/api/fusion/ai/step",
            json={"symbol": "spy", "equity": 20000, "open_positions": 0, "has_position": False},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "SPY"
        assert data["trained_profile_applied"] is True
        assert data["price"] == 512.4
        agents = [entry["agent"] for entry in data["trail"]]
        assert agents == ["director", "quant", "risk", "execution"]
        execution = data["trail"][-1]
        assert execution["executed"] is False  # review-only: no server-side orders

    def test_risk_leg_recomputed_per_request(self, monkeypatch):
        _stub(monkeypatch)
        rich = client.post("/api/fusion/ai/step", json={"symbol": "SPY", "equity": 20000, "equity_start": 20000})
        poor = client.post("/api/fusion/ai/step", json={"symbol": "SPY", "equity": 500, "equity_start": 20000})
        assert rich.json()["trail"][2]["approved"] is True
        assert rich.json()["trail"][2]["reason"] == "ok"
        assert poor.json()["trail"][2]["approved"] is False
        assert poor.json()["trail"][2]["reason"] == "daily_loss_limit"

    def test_rejects_bad_payload(self, monkeypatch):
        _stub(monkeypatch)
        assert client.post("/api/fusion/ai/step", json={"symbol": ""}).status_code == 422
        assert (
            client.post("/api/fusion/ai/step", json={"symbol": "SPY", "equity": -5}).status_code
            == 422
        )

    def test_per_request_risk_alignment_with_a_real_config(self, monkeypatch):
        _stub(monkeypatch)
        # Default LokiConfig halts after a 3% daily drawdown: a browser ledger
        # reading 9500 against a 10000 start is declined, sized honestly.
        declined = client.post(
            "/api/fusion/ai/step", json={"symbol": "SPY", "equity": 9500, "equity_start": 10000}
        )
        assert declined.status_code == 200
        assert declined.json()["trail"][2]["reason"] == "daily_loss_limit"
        assert declined.json()["trail"][2]["approved"] is False

        # max_consecutive_losses is 3 in the default config: a 3-loss streak
        # halts the account even when the day is financially fine.
        halted = client.post(
            "/api/fusion/ai/step",
            json={"symbol": "SPY", "equity": 9900, "equity_start": 10000, "consecutive_losses": 3},
        )
        assert halted.json()["trail"][2]["reason"] == "consecutive_losses"

        # Inside the limits the fresh agent approves a real sized BUY.
        healthy = client.post(
            "/api/fusion/ai/step",
            json={"symbol": "SPY", "equity": 9900, "equity_start": 10000, "consecutive_losses": 2},
        )
        decision = healthy.json()["trail"][2]
        assert decision["approved"] is True
        assert decision["reason"] == "ok"
        assert decision["action"] == "BUY"
        assert decision["qty"] > 0
        assert decision["stop"] == 498.0

    def test_step_never_mutates_the_shared_pipeline(self, monkeypatch):
        built = []

        def fake_pipeline(symbol):
            pipeline = FakePipeline()
            built.append(pipeline)
            return (pipeline, LokiConfig(), True)

        monkeypatch.setattr(ai_paper, "_analyze", lambda symbol: dict(ANALYSIS))
        monkeypatch.setattr(ai_paper, "_get_pipeline", fake_pipeline)
        first = client.post(
            "/api/fusion/ai/step",
            json={"symbol": "SPY", "equity": 9000, "equity_start": 10000, "consecutive_losses": 2},
        )
        second = client.post(
            "/api/fusion/ai/step",
            json={"symbol": "SPY", "equity": 6000, "equity_start": 10000, "consecutive_losses": 3},
        )
        assert first.status_code == second.status_code == 200
        # The second request's shared pipeline default: untouched. Its own
        # risk manager saw no reset, no streak injection, no day baseline.
        manager = built[1].risk.risk
        assert manager.day_start_equity == 100000.0
        assert manager._consecutive_losses == 0
        assert manager.resets == []

        # And each request's own ledger stays its own: the second request
        # (3 losses, 40% drawdown) reads only ITS payload, not the first's.
        assert second.json()["trail"][2]["reason"] == "daily_loss_limit"


# --- /api/fusion/ai/bars -----------------------------------------------------

ROWS = [
    ("2026-01-05", 100.0, 104.0, 99.0, 103.0, 1000.0),
    ("2026-01-06", 103.0, 106.0, 101.0, 105.0, 1200.0),
    ("2026-01-07", 105.0, 107.0, 102.0, 106.5, 900.0),
    ("2026-01-08", 106.5, 109.0, 104.5, 108.0, 1500.0),
]


class FakeProvider:
    def __init__(self, frame=None, error=None):
        self.frame = frame
        self.error = error
        self.calls = []

    def fetch_history(self, symbol, period, timeframe):
        self.calls.append((symbol, period, timeframe))
        if self.error is not None:
            raise self.error
        return self.frame


def _frame(rows=ROWS):
    index = pd.DatetimeIndex([pd.Timestamp(row[0]) for row in rows])
    return pd.DataFrame(
        [
            {"open": row[1], "high": row[2], "low": row[3], "close": row[4], "volume": row[5]}
            for row in rows
        ],
        index=index,
    )


def _bars_stub(monkeypatch, provider):
    monkeypatch.setattr(
        ai_paper,
        "_get_pipeline",
        lambda symbol: (FakePipeline(provider=provider), LokiConfig(period="1y"), True),
    )


class TestBars:
    def test_completed_candles_newest_last_in_engine_contract(self, monkeypatch):
        provider = FakeProvider(frame=_frame())
        _bars_stub(monkeypatch, provider)
        response = client.get("/api/fusion/ai/bars?symbol=spy")
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "SPY"
        assert data["period"] == "1y"
        assert data["timeframe"] == "1d"
        assert data["kind"] == "provider_candles"
        assert data["latest_bar_may_be_incomplete"] is True
        assert data["count"] == 4
        # Ascending order, newest LAST: exactly the provider's contract.
        assert [candle["t"] for candle in data["candles"]] == [
            row[0] + "T00:00:00" for row in ROWS
        ]
        assert data["candles"][-1] == {
            "t": "2026-01-08T00:00:00",
            "o": 106.5,
            "h": 109.0,
            "l": 104.5,
            "c": 108.0,
            "v": 1500.0,
        }
        # The same fetch the step analysis uses, cache-shared.
        assert provider.calls == [("SPY", "1y", "1d")]
        assert response.headers["cache-control"] == "private, no-store"
        assert "not a live quote" in data["note"]

    def test_limit_caps_to_the_newest_tail(self, monkeypatch):
        stamps = [stamp.strftime("%Y-%m-%d") for stamp in pd.bdate_range("2026-01-01", periods=70)]
        rows = [(stamp, 1.0, 2.0, 0.5, 1.5, 10.0) for stamp in stamps]
        provider = FakeProvider(frame=_frame(rows))
        _bars_stub(monkeypatch, provider)
        response = client.get("/api/fusion/ai/bars?symbol=SPY")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 60  # default cap
        candle_stamps = [candle["t"] for candle in data["candles"]]
        assert candle_stamps[0] == stamps[10] + "T00:00:00"  # the FIRST row of the tail
        assert candle_stamps[-1] == stamps[69] + "T00:00:00"  # newest candle kept last

    def test_malformed_rows_are_skipped_never_invented(self, monkeypatch):
        rows = [list(row) for row in ROWS]
        rows[1] = ["2026-01-06", float("nan"), 106.0, 101.0, 105.0, 1200.0]
        rows.append(["2026-01-09", "oops", 109.0, 104.0, 107.0, 800.0])
        provider = FakeProvider(frame=_frame([tuple(row) for row in rows]))
        _bars_stub(monkeypatch, provider)
        data = client.get("/api/fusion/ai/bars?symbol=SPY").json()
        stamps = [candle["t"] for candle in data["candles"]]
        assert data["count"] == 3
        assert "2026-01-06T00:00:00" not in stamps
        assert "2026-01-09T00:00:00" not in stamps

    def test_provider_failure_answers_503_with_human_copy(self, monkeypatch):
        provider = FakeProvider(error=RuntimeError("provider down"))
        _bars_stub(monkeypatch, provider)
        failed = client.get("/api/fusion/ai/bars?symbol=SPY")
        assert failed.status_code == 503
        assert "unavailable" in failed.json()["detail"]
        assert "SPY" in failed.json()["detail"]

    def test_empty_or_all_malformed_data_answers_503(self, monkeypatch):
        empty = FakeProvider(frame=_frame([]))
        _bars_stub(monkeypatch, empty)
        assert client.get("/api/fusion/ai/bars?symbol=SPY").status_code == 503

        junk = FakeProvider(frame=_frame([("2026-01-05", None, None, None, None, None)]))
        _bars_stub(monkeypatch, junk)
        assert client.get("/api/fusion/ai/bars?symbol=SPY").status_code == 503

    def test_input_bounds(self, monkeypatch):
        provider = FakeProvider(frame=_frame())
        _bars_stub(monkeypatch, provider)
        assert client.get("/api/fusion/ai/bars?symbol=" + "S" * 13).status_code == 422
        assert client.get("/api/fusion/ai/bars?symbol=SPY&limit=5").status_code == 422
        assert client.get("/api/fusion/ai/bars?symbol=SPY&limit=121").status_code == 422
        assert client.get("/api/fusion/ai/bars?symbol=SPY&timeframe=2m").status_code == 422

    def test_intraday_futures_and_malformed_geometry(self, monkeypatch):
        frame = _frame().iloc[::-1]
        frame.loc[frame.index[0], "high"] = 1  # impossible OHLC
        provider = FakeProvider(frame=frame)
        _bars_stub(monkeypatch, provider)
        response = client.get("/api/fusion/ai/bars?symbol=NQ%3DF&timeframe=5m")
        assert response.status_code == 200
        data = response.json()
        assert provider.calls == [("NQ=F", "1mo", "5m")]
        assert data["count"] == 3
        assert [c["t"] for c in data["candles"]] == sorted(c["t"] for c in data["candles"])
        assert data["as_of"] == data["candles"][-1]["t"]
        assert "not a Lucid execution feed" in data["note"]
