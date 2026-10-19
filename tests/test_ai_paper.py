"""AI paper-trading step endpoint: review-only pipeline, paper fills in browser."""

from fastapi.testclient import TestClient

from loki.api import ai_paper
from loki.api.server import app

client = TestClient(app)


class FakeRisk:
    def run(self, posture, signal, equity, open_positions, price):
        if signal is None:
            return {"approved": False, "reason": "no_signal"}
        if equity < 1000:
            return {"approved": False, "reason": "insufficient_equity"}
        return {"approved": True, "reason": "ok", "action": signal["action"], "qty": 37.0}


class FakePipeline:
    risk = FakeRisk()


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
    monkeypatch.setattr(ai_paper, "_build_pipeline", lambda symbol: (FakePipeline(), None, True))


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
        rich = client.post("/api/fusion/ai/step", json={"symbol": "SPY", "equity": 20000})
        poor = client.post("/api/fusion/ai/step", json={"symbol": "SPY", "equity": 500})
        assert rich.json()["trail"][2]["approved"] is True
        assert poor.json()["trail"][2]["approved"] is False
        assert poor.json()["trail"][2]["reason"] == "insufficient_equity"

    def test_rejects_bad_payload(self, monkeypatch):
        _stub(monkeypatch)
        assert client.post("/api/fusion/ai/step", json={"symbol": ""}).status_code == 422
        assert (
            client.post("/api/fusion/ai/step", json={"symbol": "SPY", "equity": -5}).status_code
            == 422
        )
