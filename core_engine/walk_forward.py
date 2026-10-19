"""Leakage-aware walk-forward validation utilities.

This module intentionally evaluates strategies through an injected evaluator. It
never assumes that an in-sample score is evidence of live profitability. The
gap between train and test windows is a purge/embargo period that prevents
features or labels near the boundary from leaking across folds.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class WalkForwardFold:
    """One ordered train/test split."""

    fold: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int


@dataclass
class WalkForwardReport:
    """Aggregated out-of-sample validation output."""

    folds: List[Dict[str, int]]
    fold_results: List[Dict[str, Any]]
    summary: Dict[str, float]
    robust: bool
    rejection_reasons: List[str]


class PurgedWalkForwardValidator:
    """Expanding-window walk-forward splitter with a mandatory gap.

    ``gap`` should be at least the maximum look-ahead horizon or label horizon
    used by the strategy. Unlike shuffled cross-validation, every test window
    occurs strictly after its corresponding training window.
    """

    def __init__(
        self,
        n_splits: int = 5,
        test_size: Optional[int] = None,
        gap: int = 1,
        min_train_size: int = 100,
        min_positive_folds: Optional[int] = None,
        min_median_sharpe: float = 0.0,
    ) -> None:
        for name, value in (
            ("n_splits", n_splits),
            ("gap", gap),
            ("min_train_size", min_train_size),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
        if test_size is not None and (
            isinstance(test_size, bool) or not isinstance(test_size, int) or test_size < 1
        ):
            raise ValueError("test_size must be a positive integer")
        if min_positive_folds is None:
            min_positive_folds = min(3, n_splits)
        if n_splits < 2:
            raise ValueError("n_splits must be at least 2")
        if gap < 0 or min_train_size < 1:
            raise ValueError("gap must be non-negative and min_train_size positive")
        if min_positive_folds < 1 or min_positive_folds > n_splits:
            raise ValueError("min_positive_folds must be within the split count")
        if not np.isfinite(min_median_sharpe):
            raise ValueError("min_median_sharpe must be finite")
        self.n_splits = n_splits
        self.test_size = test_size
        self.gap = gap
        self.min_train_size = min_train_size
        self.min_positive_folds = min_positive_folds
        self.min_median_sharpe = min_median_sharpe

    def split(self, n_samples: int) -> Iterator[WalkForwardFold]:
        """Yield chronological folds without train/test overlap."""
        if n_samples < self.min_train_size + self.gap + self.n_splits:
            raise ValueError("Not enough observations for requested walk-forward configuration")
        test_size = self.test_size or (n_samples - self.min_train_size - self.gap) // self.n_splits
        if test_size < 1:
            raise ValueError("test_size must be positive")
        first_test_start = n_samples - self.n_splits * test_size
        for fold in range(self.n_splits):
            test_start = first_test_start + fold * test_size
            test_end = min(test_start + test_size, n_samples)
            train_end = test_start - self.gap
            if train_end < self.min_train_size:
                raise ValueError("Fold would violate min_train_size")
            yield WalkForwardFold(
                fold=fold,
                train_start=0,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
            )

    def evaluate(
        self,
        data: pd.DataFrame,
        evaluator: Callable[[pd.DataFrame, pd.DataFrame, int], Mapping[str, Any]],
    ) -> WalkForwardReport:
        """Evaluate each fold and summarize only forward test results.

        The evaluator must return a mapping. If it returns ``sharpe_ratio`` or
        ``total_return``, those values are included in robustness summaries.
        """
        if not isinstance(data, pd.DataFrame):
            raise TypeError("data must be a pandas DataFrame")
        if not data.index.is_monotonic_increasing or not data.index.is_unique:
            raise ValueError("data index must be sorted and unique (sorted chronologically)")
        folds = list(self.split(len(data)))
        results: List[Dict[str, Any]] = []
        reasons: List[str] = []
        for fold in folds:
            train = data.iloc[fold.train_start : fold.train_end].copy()
            test = data.iloc[fold.test_start : fold.test_end].copy()
            output = dict(evaluator(train, test, fold.fold))
            output["fold"] = fold.fold
            for key in ("total_return", "sharpe_ratio"):
                try:
                    valid = key in output and np.isfinite(float(output[key]))
                except (TypeError, ValueError, OverflowError):
                    valid = False
                if not valid:
                    reasons.append(f"fold {fold.fold} has missing or non-finite {key}")
            results.append(output)

        summary: Dict[str, float] = {"fold_count": float(len(results))}
        for key in ("sharpe_ratio", "total_return", "max_drawdown"):
            clean = []
            for result in results:
                try:
                    value = float(result[key])
                    if np.isfinite(value):
                        clean.append(value)
                except (KeyError, TypeError, ValueError, OverflowError):
                    continue
            values = np.asarray(clean)
            if values.size:
                summary[f"{key}_median"] = float(np.median(values))
                summary[f"{key}_mean"] = float(np.mean(values))
                summary[f"{key}_worst"] = float(
                    np.min(values) if key != "max_drawdown" else np.min(values)
                )

        positive_returns = 0
        for result in results:
            try:
                value = float(result.get("total_return", 0.0))
                positive_returns += bool(np.isfinite(value) and value > 0)
            except (TypeError, ValueError, OverflowError):
                continue
        summary["positive_return_fraction"] = positive_returns / len(results)
        robust = not reasons
        if positive_returns < self.min_positive_folds:
            robust = False
            reasons.append("too few positive out-of-sample folds")
        if summary.get("sharpe_ratio_median", -np.inf) < self.min_median_sharpe:
            robust = False
            reasons.append("median out-of-sample Sharpe is below threshold")
        return WalkForwardReport(
            folds=[asdict(fold) for fold in folds],
            fold_results=results,
            summary=summary,
            robust=robust,
            rejection_reasons=reasons,
        )
