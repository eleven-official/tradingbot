"""Research controls for reproducible, cost-aware strategy evaluation.

This module does not place orders. It records the number of strategy trials,
compares a strategy with a baseline, and runs explicit execution-cost scenarios.
It is intentionally conservative: missing metrics are reported as missing rather
than being silently treated as evidence of a profitable strategy.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class TrialRecord:
    strategy_name: str
    parameter_hash: str
    data_id: str
    started_at: str
    notes: str = ""


@dataclass
class StressScenarioResult:
    multiplier: float
    result: Dict[str, Any]


class ResearchHarness:
    """Small deterministic harness around an injected replay evaluator."""

    def __init__(self, data_id: str, random_seed: int = 0) -> None:
        if not str(data_id).strip():
            raise ValueError("data_id is required for reproducible research")
        self.data_id = str(data_id)
        self.random_seed = int(random_seed)
        self.trials: list[TrialRecord] = []

    def record_trial(self, strategy_name: str, parameter_hash: str, notes: str = "") -> TrialRecord:
        """Record a candidate before seeing its score, preventing hidden trial counts."""
        record = TrialRecord(
            strategy_name=str(strategy_name),
            parameter_hash=str(parameter_hash),
            data_id=self.data_id,
            started_at=datetime.now(timezone.utc).isoformat(),
            notes=str(notes),
        )
        self.trials.append(record)
        return record

    def trial_ledger(self) -> list[Dict[str, str]]:
        return [asdict(record) for record in self.trials]

    @staticmethod
    def baseline_returns(prices: pd.Series) -> pd.Series:
        """Buy-and-hold daily returns from a validated close-price series."""
        close = pd.to_numeric(prices, errors="coerce")
        if close.empty or not np.isfinite(close.to_numpy(dtype=float)).all() or (close <= 0).any():
            raise ValueError("baseline prices must be finite and positive")
        return close.pct_change().dropna()

    @staticmethod
    def summary(returns: pd.Series, periods_per_year: int = 252) -> Dict[str, float]:
        """Return conservative core metrics, including cost-neutral diagnostics."""
        if isinstance(periods_per_year, bool) or not isinstance(periods_per_year, int) or periods_per_year < 1:
            raise ValueError("periods_per_year must be a positive integer")
        values = pd.to_numeric(returns, errors="coerce").astype(float)
        if values.empty or not np.isfinite(values.to_numpy()).all() or (values < -1).any():
            raise ValueError("returns must contain finite observations")
        equity = (1.0 + values).cumprod()
        # Capital exists before the first return; an immediate loss must count.
        peak = equity.cummax().clip(lower=1.0)
        drawdown = equity / peak - 1.0
        annualized_return = float(equity.iloc[-1] ** (periods_per_year / len(values)) - 1.0)
        volatility = float(values.std(ddof=1) * np.sqrt(periods_per_year)) if len(values) > 1 else 0.0
        sharpe = float(values.mean() / values.std(ddof=1) * np.sqrt(periods_per_year)) if values.std(ddof=1) > 0 else 0.0
        downside_deviation = float(np.sqrt(np.square(values.clip(upper=0)).mean()))
        sortino = float(values.mean() / downside_deviation * np.sqrt(periods_per_year)) if downside_deviation > 0 else 0.0
        max_dd = float(drawdown.min())
        return {
            "total_return": float(equity.iloc[-1] - 1.0),
            "annualized_return": annualized_return,
            "volatility": volatility,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "max_drawdown": max_dd,
            "calmar_ratio": annualized_return / abs(max_dd) if max_dd < 0 else 0.0,
            "observations": float(len(values)),
        }

    def run_cost_stress(
        self,
        evaluator: Callable[[float, int], Mapping[str, Any]],
        multipliers: Sequence[float] = (1.0, 1.5, 2.0, 3.0),
    ) -> list[StressScenarioResult]:
        """Run deterministic slippage/cost scenarios through an injected evaluator."""
        clean = [float(value) for value in multipliers]
        if not clean or any(not np.isfinite(value) or value <= 0 for value in clean):
            raise ValueError("stress multipliers must be finite and positive")
        return [StressScenarioResult(value, dict(evaluator(value, self.random_seed))) for value in clean]

    @staticmethod
    def compare_to_baseline(strategy_returns: pd.Series, baseline_returns: pd.Series) -> Dict[str, Any]:
        """Compare aligned return series without claiming statistical significance."""
        aligned = pd.concat([strategy_returns.rename("strategy"), baseline_returns.rename("baseline")], axis=1).dropna()
        if aligned.empty:
            raise ValueError("strategy and baseline have no aligned observations")
        strategy = ResearchHarness.summary(aligned["strategy"])
        baseline = ResearchHarness.summary(aligned["baseline"])
        return {
            "strategy": strategy,
            "baseline": baseline,
            "excess_total_return": strategy["total_return"] - baseline["total_return"],
            "aligned_observations": len(aligned),
        }
