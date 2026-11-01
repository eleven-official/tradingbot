"""Fixed daily rules shared by retrospective research and paper execution.

Signals use completed bars only. Entry and holding conditions are distinct so
a pullback entry does not become an automatic exit on the next heartbeat.
"""
from dataclasses import asdict, dataclass
import math


VERSION = "loki_daily_regime_v2"
WARMUP = 200


@dataclass(frozen=True)
class Rule:
    name: str
    fast: int
    slow: int
    stop_pct: float
    take_profit_pct: float
    max_holding_sessions: int
    max_volatility: float = 0.40

    def policy(self):
        return {
            "allocation": 0.10,
            "max_notional": 1000.0,
            "risk_per_trade": 0.005,
            "stop_pct": self.stop_pct,
            "take_profit_pct": self.take_profit_pct,
            "max_holding_sessions": self.max_holding_sessions,
            "fee_bps": 10.0,
            "slippage_bps": 5.0,
        }


# Versioned hypotheses. Add stricter lower-turnover variants.
RULES = (
    Rule("trend_50_200", 50, 200, 0.06, 0.18, 63),
    Rule("momentum_20_100", 20, 100, 0.04, 0.12, 42),
    Rule("pullback_5_100", 5, 100, 0.03, 0.06, 10),
    Rule("trend_20_50", 20, 50, 0.04, 0.10, 21),
    Rule("trend_10_30", 10, 30, 0.03, 0.07, 14),
)


def get_rule(name):
    for rule in RULES:
        if rule.name == name:
            return rule
    raise ValueError("Unknown versioned daily rule")


def frozen_rule(rule):
    return {"version": VERSION, "rule": asdict(rule), "policy": rule.policy()}


def validate_artifact(artifact):
    if artifact.get("version") != VERSION:
        raise ValueError("Unsupported daily rule version")
    rule = get_rule(artifact.get("rule", {}).get("name"))
    if artifact.get("rule") != asdict(rule) or artifact.get("policy") != rule.policy():
        raise ValueError("Daily rule or risk policy differs from its frozen version")
    if artifact.get("threshold") not in (None, 1.0):
        raise ValueError("Daily rules use a binary entry condition, not a probability")
    return rule


def signal_series(bars, rule):
    """O(n) causal features; result i uses bars through i, never i+1."""
    closes = [bar.close for bar in bars]
    sums = [0.0]
    returns, squares = [0.0], [0.0]
    for i, close in enumerate(closes):
        sums.append(sums[-1] + close)
        change = close / closes[i - 1] - 1 if i else 0.0
        returns.append(returns[-1] + change)
        squares.append(squares[-1] + change * change)
    result = []
    for i, close in enumerate(closes):
        if i < WARMUP:
            result.append({"enter": False, "hold": False, "ready": False})
            continue
        end = i + 1
        average = lambda window: (sums[end] - sums[end - window]) / window
        mean = (returns[end] - returns[end - 20]) / 20
        variance = max(0.0, (squares[end] - squares[end - 20]) / 20 - mean * mean)
        volatility = math.sqrt(252 * variance)
        bullish = close > average(rule.slow)
        if rule.name in ("trend_50_200", "trend_20_50", "trend_10_30"):
            enter = hold = bullish and average(rule.fast) > average(rule.slow)
        elif rule.name == "momentum_20_100":
            enter = hold = bullish and close > closes[i - rule.fast]
        else:
            enter = bullish and close / closes[i - rule.fast] - 1 < -0.01
            hold = bullish and close < average(10)
        result.append({
            "enter": bool(enter and volatility <= rule.max_volatility),
            "hold": bool(hold),
            "ready": True,
            "volatility": volatility,
        })
    return result


def decision(artifact, bars):
    rule = validate_artifact(artifact)
    if len(bars) <= WARMUP:
        raise ValueError("Daily regime rules require 201 completed daily bars")
    signal = signal_series(bars, rule)[-1]
    if artifact["threshold"] is None:
        signal.update(enter=False, hold=False)
    return signal


def notional_budget(policy, equity, cash, ceiling):
    """Cash, allocation and loss-at-stop budget, shared by replay and runner."""
    if any(not math.isfinite(value) or value < 0 for value in (equity, cash, ceiling)):
        raise ValueError("Position budget needs finite nonnegative account values")
    return min(
        ceiling, policy["max_notional"], equity * policy["allocation"], cash,
        equity * policy["risk_per_trade"] / policy["stop_pct"],
    )
