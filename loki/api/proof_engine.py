"""The Proof Engine: a plain-English idea becomes transparent rules, the
rules meet an attempt at falsification, and the outcome is a reproducible
evidence report — never a promise.

The three steps the platform audit asked for, mapped to machinery that
already exists:

1. Describe a strategy in plain English.
2. The engine converts it to *exactly* the fixed rules the paper replay
   runs (deterministic keyword classification, and it says so — unknown
   fragments are surfaced, never invented around).
3. Loki tries to prove the idea wrong: chronological train/holdout splits,
   a harsher-cost battery (2x/3x fee and slippage), transfer and cost
   robustness checks, a declared drawdown limit when one is named, and a
   buy-and-hold benchmark comparison.

Nothing here forecasts prices or promises income. The report exists so a
visitor can see why an idea is rejected — which is most of the time, by
design, because most ideas fail the checks.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import Any, Mapping, Sequence

from loki.api import proof_rate_store
from loki.api.strategy_backtest import (
    BacktestInputError,
    STRATEGY_NAMES,
    run_strategy_backtest,
)

# Bumped with every methodology change: thresholds, verdict bands, fingerprint
# scope, declared-value handling. Old fingerprints were compiled under the old
# methodology and are comparable only against reports stamped with it.
PROOF_VERSION = "proof-2.0.0"

_REVISION_ENV_VARS = ("VERCEL_GIT_COMMIT_SHA", "RENDER_GIT_COMMIT", "GITHUB_SHA")


def method_revision() -> str:
    """The deployed revision the run executed under, or an honest local marker.

    Read at report time so each evidence report names the exact code revision,
    not assumptions about when the process was built.
    """
    for var in _REVISION_ENV_VARS:
        value = os.environ.get(var)
        if value:
            return value
    return "unversioned-local"


BATTERY = (
    ("base", 10.0, 5.0),
    ("harsher", 20.0, 10.0),
    ("harshest", 30.0, 15.0),
)

_MIN_HOLDOUT_TRADES = 3  # below this the sample cannot speak
_PROVISIONAL_TRADES = 8  # thin: enough to read, never enough to support
_SUPPORTED_TRADES = 15  # a supported verdict wants this many holdout trades

# Abuse protection for /api/proof/assess: each run is three replays plus a
# public-feed fetch, so the door shuts per identity before it gets expensive.
# Where the counters live (per-process memory vs a shared Upstash Redis) is
# the rate store's decision; this module only forwards.
PROOF_RATE_WINDOW_SECONDS = proof_rate_store.PROOF_RATE_WINDOW_SECONDS
PROOF_RATE_MAX_PER_WINDOW = proof_rate_store.PROOF_RATE_MAX_PER_WINDOW
rate_store = proof_rate_store.select_backend()


def rate_limited(key: str, now: float | None = None) -> bool:
    """True when the key has used up its run quota in the current window."""
    return rate_store.hit(key, now)


def reset_rate_limiter() -> None:
    rate_store.reset()


_FAMILY_WORDS = {
    "trend_following": (
        "momentum",
        "trend",
        "trending",
        "trailing",
        "moving average",
        "moving-average",
        "ema",
        "sma",
        "continuation",
    ),
    "breakout": (
        "breakout",
        "break out",
        "break-out",
        "range break",
        "resistance",
        "new high",
        "level",
        "volume confirmed",
        "volume-confirmed",
    ),
    "pullback_reclaim": (
        "pullback",
        "pull-back",
        "dip",
        "reclaim",
        "bounce",
        "oversold",
        "buy the dip",
        "buy-the-dip",
    ),
}

_DRAWDOWN_RE = re.compile(
    r"drawdown(?:\s+limit)?(?:\s+(?:of|under|below|max|maximum|at most|less than))?\s*"
    r"(?:max(?:imum)?\s+)?(\d+(?:\.\d+)?)\s*%"
    # Also accept the reversed order, e.g. "a strict 25% drawdown limit",
    # so the number's position never decides whether the limit exists.
    r"|\b(\d+(?:\.\d+)?)\s*%\s+(?:one-candle\s+|overall\s+|daily\s+)?drawdown",
    re.IGNORECASE,
)
_CAPITAL_RE = re.compile(r"\$\s*(\d[\d,]*)|(\d[\d,]*)\s*(?:dollars|usd|usdt)\b", re.IGNORECASE)
_RISK_RE = re.compile(r"risk(?:ing)?\s*(\d+(?:\.\d+)?)\s*%", re.IGNORECASE)


class ProofError(ValueError):
    """A description the engine honestly cannot compile."""


def _family_match(word: str, lowered: str) -> bool:
    """Whole-word keyword match with an optional plural 's'.

    Substring checks misfire on nested text ('sma' inside 'small') and the
    conflict detector makes every misfire visible, so matching honors word
    boundaries instead.
    """
    return re.search(rf"(?<!\w){re.escape(word)}s?(?!\w)", lowered) is not None


def _parse_description(description: str) -> tuple[str, list[str]]:
    if not isinstance(description, str) or not description.strip():
        raise ProofError("Describe the idea in words — the engine compiles text, not silence.")
    if len(description) > 2000:
        raise ProofError("Keep the description under 2000 characters.")
    lowered = description.lower()
    matched_pairs: list[tuple[str, str]] = []
    seen_families: dict[str, list[str]] = {}
    for family, words in _FAMILY_WORDS.items():
        matched_words = [word for word in words if _family_match(word, lowered)]
        if matched_words:
            seen_families[family] = matched_words
            matched_pairs.append((family, matched_words[0]))
    if not matched_pairs:
        raise ProofError(
            "No supported rule family found. Name the idea in terms the replay runs: "
            "momentum / trend (EMA trend continuation), breakout "
            "(Volume-confirmed breakout), or pullback reclaim "
            "(Trend pullback reclaim)."
        )
    if len(seen_families) > 1:
        # A multiply-classified description would run rules the user never
        # meant — refuse and name both, rather than letting the word map
        # silently pick the first family it happens to check.
        listed = "; ".join(
            f"{family} ({STRATEGY_NAMES[family]}) via the word '{word}'"
            for family, word in matched_pairs
        )
        raise ProofError(
            "The description names more than one rule family at once — "
            f"{listed}. The engine does not silently pick between them: "
            "name exactly one in terms the replay runs."
        )
    family = matched_pairs[0][0]
    return family, seen_families[family]


def compile_spec(description: str) -> dict[str, Any]:
    """Plain English -> exactly the rules the replay will run.

    Deterministic keyword classification. Whatever the replay will do is
    written out in words; anything in the description the replay does NOT
    do is listed under ``not modelled`` so nothing is silently ignored.
    """
    family, matched = _parse_description(description)
    not_modelled: list[str] = []
    if re.search(r"\bshort\b|\bshorts?\b|\bsell\b", description.lower()):
        not_modelled.append("short selling — this replay is long-only")
    indicators = re.findall(
        r"\b(macd|bollinger|ichimoku|stochastic|vwap|order book|fundamentals)\b",
        description.lower(),
    )
    for name in sorted(set(indicators)):
        not_modelled.append(f"{name.upper()} — not part of the fixed rule set")
    if re.search(r"\bintraday scalping?\b", description.lower()):
        not_modelled.append("scalping execution assumptions — replay uses fixed bar fills")
    declared_drawdown: float | None = None
    drawdown_match = _DRAWDOWN_RE.search(description)
    if drawdown_match:
        # Two accepted orders; exactly one of the two groups is filled.
        declared_drawdown = float(drawdown_match.group(1) or drawdown_match.group(2))
    declared_risk: float | None = None
    risk_match = _RISK_RE.search(description)
    if risk_match:
        declared_risk = float(risk_match.group(1))
    declared_capital: float | None = None
    capital_match = _CAPITAL_RE.search(description)
    if capital_match:
        # Two forms: "$N" fills group 1; "N dollars/usd/usdt" fills group 2.
        digits = capital_match.group(1) or capital_match.group(2)
        declared_capital = float(digits.replace(",", ""))
    spec = {
        "compiler": "deterministic keyword classification; not comprehension; edit this description between runs to change what runs",
        "matched_words": matched,
        "family": family,
        "family_name": STRATEGY_NAMES[family],
        "entry_rule": (
            "train/indicator conditions from the fixed rule family above, on completed candles; "
            "entry fills on the next candle open with adverse slippage"
        ),
        "exit_rule": "protective stop at entry minus 1.5 ATR, target at entry plus 3.0 ATR (2-to-1), earliest touched wins; ambiguous same-candle touch scores as stop; time exit if neither",
        "sizing_rule": (
            "fixed-percent risk sizing per trade, capped by available equity; "
            "drawdown limits are measured as overall peak-to-trough equity decline, not per candle"
        ),
        "not_modelled": not_modelled,
    }
    if declared_drawdown is not None:
        spec["declared_drawdown_limit"] = declared_drawdown
    else:
        not_modelled.append("any drawdown limit — none was declared in words")
    if declared_risk is not None:
        # Out-of-band values are evaluated (and refused) at replay time in
        # assess(); compile only records what the words said.
        spec["declared_risk_percent"] = declared_risk
    else:
        not_modelled.append("per-trade risk — none was declared in words; the default is applied")
    if declared_capital is not None:
        spec["declared_capital"] = declared_capital
    else:
        not_modelled.append("starting capital — none was declared in words; the default is applied")
    return spec


def _check(name: str, status: str, detail: str) -> dict[str, str]:
    return {"check": name, "status": status, "detail": detail}


def run_battery(
    candles: Sequence[Mapping[str, Any]],
    family: str,
    starting_capital: float,
    risk_percent: float,
    max_holding_bars: int,
) -> list[dict[str, Any]]:
    """One fixed rule set, replayed at each cost level. Parameters do not move."""
    runs = []
    for label, fee, slippage in BATTERY:
        result = run_strategy_backtest(
            candles,
            family,
            starting_capital=starting_capital,
            risk_percent=risk_percent,
            fee_bps=fee,
            slippage_bps=slippage,
            max_holding_bars=max_holding_bars,
        )
        runs.append(
            {
                "run": label,
                "fee_bps": fee,
                "slippage_bps": slippage,
                "training": result["training"],
                "holdout": result["out_of_sample"],
                "benchmark_holdout_return_percent": result["out_of_sample"][
                    "buy_hold_return_percent"
                ],
            }
        )
    return runs


def attempt_falsification(
    spec: dict[str, Any], battery: list[dict[str, Any]]
) -> list[dict[str, str]]:
    """Deterministic checks a strategy must survive to earn support."""
    checks: list[dict[str, str]] = []
    base = battery[0]["holdout"]
    hardest = battery[-1]["holdout"]
    train = battery[0]["training"]
    trades = base["trade_count"]

    if trades < _MIN_HOLDOUT_TRADES:
        checks.append(
            _check(
                "holdout_sample_size",
                "insufficient",
                f"Only {trades} closed holdout trades — below {_MIN_HOLDOUT_TRADES}, the window cannot speak.",
            )
        )
    elif trades < _PROVISIONAL_TRADES:
        checks.append(
            _check(
                "holdout_sample_size",
                "watch",
                f"{trades} closed holdout trades — too thin to establish anything; at least {_PROVISIONAL_TRADES} for a readable result, {_SUPPORTED_TRADES}+ for full support.",
            )
        )
    elif trades < _SUPPORTED_TRADES:
        checks.append(
            _check(
                "holdout_sample_size",
                "watch",
                f"{trades} closed holdout trades — enough to read, not enough on its own to establish an edge (want {_SUPPORTED_TRADES}+).",
            )
        )
    else:
        checks.append(
            _check(
                "holdout_sample_size",
                "pass",
                f"{trades} closed holdout trades on unseen chronological bars.",
            )
        )

    expectancy = base["expectancy_r"]
    if trades >= _MIN_HOLDOUT_TRADES:
        if expectancy <= 0:
            checks.append(
                _check(
                    "after_cost_edge",
                    "fail",
                    f"Average holdout trade expectancy is {expectancy}R after base costs — no edge survives the fees.",
                )
            )
        else:
            checks.append(
                _check(
                    "after_cost_edge",
                    "pass",
                    f"Average holdout trade expectancy is {expectancy}R after base costs.",
                )
            )
        train_expectancy = train["expectancy_r"]
        if train_expectancy > 0 and expectancy <= 0:
            checks.append(
                _check(
                    "transfer",
                    "fail",
                    "Profitable in training, not in the untouched holdout — the overfit signature.",
                )
            )
        elif train_expectancy > 0 and expectancy < 0.5 * train_expectancy:
            checks.append(
                _check(
                    "transfer",
                    "watch",
                    f"Holdout expectancy ({expectancy}R) keeps less than half of training's ({train_expectancy}R).",
                )
            )
        else:
            checks.append(
                _check(
                    "transfer",
                    "pass",
                    "Holdout behaviour is consistent with training; no degradation signature to flag.",
                )
            )
        hardest_expectancy = hardest["expectancy_r"]
        if hardest_expectancy > 0:
            checks.append(
                _check(
                    "cost_robustness",
                    "pass",
                    "Positive holdout expectancy survives 3x fee and slippage assumptions.",
                )
            )
        else:
            checks.append(
                _check(
                    "cost_robustness",
                    "fail",
                    f"At 3x fee and slippage assumptions expectancy flips to {hardest_expectancy}R — the edge dies with costs.",
                )
            )
        if spec.get("declared_drawdown_limit") is not None:
            limit = float(spec["declared_drawdown_limit"])
            observed_dd = base["max_drawdown_percent"]
            if observed_dd <= limit:
                checks.append(
                    _check(
                        "declared_drawdown_respected",
                        "pass",
                        f"Holdout peak-to-trough drawdown {observed_dd}% stayed within the declared overall {limit}% limit.",
                    )
                )
            else:
                checks.append(
                    _check(
                        "declared_drawdown_respected",
                        "fail",
                        f"Holdout peak-to-trough drawdown {observed_dd}% breached the declared overall {limit}% limit. "
                        "(Measured as the deepest equity decline across the window, not per candle or per trade.)",
                    )
                )
        else:
            checks.append(
                _check(
                    "declared_drawdown_respected",
                    "watch",
                    f"No drawdown limit declared in the description; holdout overall peak-to-trough drawdown was {base['max_drawdown_percent']}%.",
                )
            )
        edge = base["net_return_percent"] - battery[0]["benchmark_holdout_return_percent"]
        if edge > 0:
            checks.append(
                _check(
                    "benchmark_comparison",
                    "pass",
                    f"Holdout net return {base['net_return_percent']}% beat buy-and-hold ({battery[0]['benchmark_holdout_return_percent']}%) on the same window.",
                )
            )
        elif edge >= -2.0:
            checks.append(
                _check(
                    "benchmark_comparison",
                    "watch",
                    f"Holdout net return {base['net_return_percent']}% vs buy-and-hold {battery[0]['benchmark_holdout_return_percent']}% — roughly in line; passive held similar ground.",
                )
            )
        else:
            checks.append(
                _check(
                    "benchmark_comparison",
                    "fail",
                    f"Holdout net return {base['net_return_percent']}% clearly underperformed buy-and-hold ({battery[0]['benchmark_holdout_return_percent']}%).",
                )
            )
    return checks


def hardest_fee_bps() -> float:
    return BATTERY[-1][1]


def reviewers(checks: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    """Independent lenses over the same checks — no new numbers, new focus.
    Total: a missing check means the battery never reached it, and the
    reviewer says so instead of raising."""

    def pick(name: str) -> dict[str, str] | None:
        return next((c for c in checks if c["check"] == name), None)

    def either(name: str, absent: str) -> tuple[str, str]:
        found = pick(name)
        return (found["status"], found["detail"]) if found else ("watch", absent)

    quant_status, quant_reason = either(
        "after_cost_edge", "No quant checks were produced — the sample may be unusable."
    )
    risk_status, risk_reason = either(
        "declared_drawdown_respected", "Drawdown was not evaluated — the sample may be unusable."
    )
    exec_status, exec_reason = either(
        "cost_robustness", "Cost robustness was not evaluated — the sample may be unusable."
    )
    worst = (
        "fail"
        if any(c["status"] == "fail" for c in checks)
        else ("watch" if any(c["status"] in ("watch", "insufficient") for c in checks) else "pass")
    )
    return [
        {
            "role": "Quant reviewer",
            "verdict": quant_status,
            "reason": quant_reason,
        },
        {
            "role": "Risk reviewer",
            "verdict": risk_status,
            "reason": risk_reason,
        },
        {
            "role": "Execution reviewer",
            "verdict": exec_status,
            "reason": exec_reason,
        },
        {
            "role": "Panel",
            "verdict": worst,
            "reason": "Worst finding across the checks above; the panel's word is the verdict band, not a probability.",
        },
    ]


def verdict_for(checks: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    statuses = [c["status"] for c in checks]
    if "insufficient" in statuses or not checks:
        return {
            "status": "insufficient evidence",
            "headline": "The holdout sample cannot support a read either way.",
            "reasons": [c["detail"] for c in checks if c["status"] == "insufficient"],
        }
    if "fail" in statuses:
        fails = [c["detail"] for c in checks if c["status"] == "fail"]
        return {
            "status": "rejected",
            "headline": "The idea did not survive falsification — the reasons are listed, not hidden.",
            "reasons": fails,
        }
    if any(status == "watch" for status in statuses):
        return {
            "status": "provisional support (paper research, not advice)",
            "headline": (
                "Survived the battery with unresolved warnings — passed this limited test, "
                "not independent validation; unresolved warnings keep the verdict provisional."
            ),
            "reasons": [c["detail"] for c in checks if c["status"] == "watch"],
        }
    return {
        "status": "tested-supported (paper research, not advice)",
        "headline": (
            "Passed every check in this limited battery — that is not independent validation, "
            "it still has to live in paper before anything else, and nothing here promises income."
        ),
        "reasons": [c["detail"] for c in checks if c["status"] == "pass"],
    }


_LIMITATIONS = (
    "Historical diagnostics, not forecasts — no income is promised and past behaviour does not repeat on command.",
    "One instrument, one interval, one rule family per report: results are specific to the exact series tested.",
    "Battery costs are fixed multiples (1x/2x/3x of 10 bps fee, 5 bps slippage per side); real execution can be worse, especially at size.",
    "Both-touch candles are scored stop-first, so results are conservative — but fills, gaps and liquidity assumptions stay simplified.",
    "Walk-forward selection is not used here: this engine replays a fixed family. Strategy-search edges need the Quant lab report instead.",
    "Regimes change; a supported verdict describes the tested windows only.",
)


def fingerprint(report_inputs: Mapping[str, Any]) -> str:
    payload = json.dumps(report_inputs, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def dataset_digest(candles: Sequence[Mapping[str, Any]]) -> str:
    """sha256 over every candle value — the same series must reproduce the
    same fingerprint, and two different series with matching endpoints or
    lengths must not."""
    canonical = [
        [
            float(row["time"]),
            round(float(row["open"]), 10),
            round(float(row["high"]), 10),
            round(float(row["low"]), 10),
            round(float(row["close"]), 10),
            round(float(row["volume"]), 10),
        ]
        for row in candles
    ]
    payload = json.dumps(canonical, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def assess(
    candles: Sequence[Mapping[str, Any]],
    description: str,
    *,
    symbol: str = "",
    interval: str = "",
    starting_capital: float | None = None,
    risk_percent: float | None = None,
    max_holding_bars: int = 20,
) -> dict[str, Any]:
    """Full pass: compile, resolve the config, run the battery, falsify, report.

    Values the description declares in words win; explicit keyword arguments
    override words; the defaults apply only when neither speaks. A resolved
    value outside its band is refused, never quietly shrunk.
    """
    spec = compile_spec(description)
    risk_arg = risk_percent
    if risk_arg is None:
        risk_arg = spec.get("declared_risk_percent", 1.0)
    applied_risk = float(risk_arg)
    capital_arg = starting_capital
    if capital_arg is None:
        capital_arg = spec.get("declared_capital", 10_000.0)
    applied_capital = float(capital_arg)
    # Declared numbers are honoured exactly or refused with reasons — a
    # silent clamp would mean the replay ran something the visitor never
    # approved.
    if not 0.05 <= applied_risk <= 5.0:
        raise ProofError(
            f"declared per-trade risk {applied_risk}% sits outside the replay band of 0.05% to 5%. "
            "The engine refuses to quietly shrink a declared number — name a value inside the band."
        )
    if not 1.0 <= applied_capital <= 1e9:
        raise ProofError(
            f"declared starting capital {applied_capital} sits outside the replay band of $1 to $1,000,000,000. "
            "The engine refuses to quietly shrink a declared number — name a value inside the band."
        )
    spec["applied_risk_percent"] = applied_risk
    spec["applied_starting_capital"] = applied_capital
    runs = run_battery(candles, spec["family"], applied_capital, applied_risk, max_holding_bars)
    checks = attempt_falsification(spec, runs)
    verdict = verdict_for(checks)
    panel = reviewers(checks)
    digest = dataset_digest(candles)
    revision = method_revision()
    stamp = {
        "engine": "loki-proof-engine",
        "engine_version": PROOF_VERSION,
        "method_revision": revision,
        "spec": spec,
        "applied_starting_capital": applied_capital,
        "applied_risk_percent": applied_risk,
        "max_holding_bars": max_holding_bars,
        "battery": [list(level) for level in BATTERY],
        "data_sha256": digest,
        "symbol": (symbol or "").strip().upper(),
        "interval": interval,
        "bar_count": len(candles),
        "first_time": candles[0]["time"],
        "last_time": candles[-1]["time"],
    }
    return {
        "engine": "loki-proof-engine",
        "proof_version": PROOF_VERSION,
        "method_revision": revision,
        "mode": "evidence-report",
        "symbol": (symbol or "").strip().upper(),
        "interval": interval,
        "bar_count": len(candles),
        "spec": spec,
        "battery": runs,
        "checks": checks,
        "reviewers": panel,
        "verdict": verdict,
        "limitations": list(_LIMITATIONS),
        "repro": {
            "engine_version": PROOF_VERSION,
            "method_revision": revision,
            "dataset_rows": len(candles),
            "dataset_sha256": digest,
            "config": {
                "family": spec["family"],
                "applied_starting_capital": applied_capital,
                "applied_risk_percent": applied_risk,
                "max_holding_bars": max_holding_bars,
                "battery": [list(level) for level in BATTERY],
            },
            "first_time": candles[0]["time"],
            "last_time": candles[-1]["time"],
        },
        "fingerprint": {
            "algorithm": "sha256",
            "value": fingerprint(stamp),
            "inputs": "compiled spec with applied config, battery levels, full canonical candle values, symbol, interval, window endpoints, engine version, method revision",
        },
        "disclaimer": (
            "Evidence report, not advice and not a recommendation: describes what happened "
            "under the stated assumptions and never promises income."
        ),
    }


def safe_assess(
    candles: Sequence[Mapping[str, Any]],
    description: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """assess(), with input errors converted to ProofError-shaped text."""
    allowed = {"symbol", "interval", "starting_capital", "risk_percent", "max_holding_bars"}
    try:
        return assess(candles, description, **{k: v for k, v in kwargs.items() if k in allowed})
    except BacktestInputError as error:
        raise ProofError(str(error)) from error
