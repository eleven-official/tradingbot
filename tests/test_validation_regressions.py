"""Boundary checks for the new walk-forward feature."""
import pytest

from loki_v8.validation import pathwise_cv_indices
from loki_v8.validation import data_fingerprint, purged_kfold_indices, run_fold
from loki_v8.config import LokiConfig
import numpy as np
import pandas as pd


def test_pathwise_includes_final_complete_window():
    folds = pathwise_cv_indices(560, min_train_bars=500, test_bars=60)
    assert len(folds) == 1
    assert folds[0][1][-1] == 559


@pytest.mark.parametrize("kwargs", [{"step_bars": 0}, {"test_bars": 0}, {"purge_bars": -1}])
def test_invalid_windows_fail_instead_of_hanging(kwargs):
    with pytest.raises(ValueError):
        pathwise_cv_indices(1000, **kwargs)


def test_fingerprint_tracks_intraday_prices_volume_and_dates():
    frame = pd.DataFrame({"open": [10.0, 11.0], "high": [12.0, 12.0],
                          "low": [9.0, 10.0], "close": [11.0, 11.5],
                          "volume": [100.0, 200.0]}, index=pd.date_range("2020-01-01", periods=2))
    original = data_fingerprint(frame)
    for column in frame.columns:
        changed = frame.copy()
        changed.iloc[0, changed.columns.get_loc(column)] += 0.1
        assert data_fingerprint(changed) != original
    changed = frame.copy()
    changed.index += pd.Timedelta(days=1)
    assert data_fingerprint(changed) != original


def test_kfold_keeps_remainder_bars():
    folds = purged_kfold_indices(1003, n_splits=5)
    assert folds[-1][1][-1] == 1002


def test_kfold_rejects_zero_splits():
    with pytest.raises(ValueError):
        purged_kfold_indices(1000, n_splits=0)


def test_disjoint_test_blocks_never_include_unselected_gap():
    with pytest.raises(ValueError, match="contiguous"):
        run_fold(pd.DataFrame(), np.arange(100), np.array([200, 201, 300]),
                 {}, LokiConfig(), 252, "TEST")
