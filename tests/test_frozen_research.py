"""Reserved-sample audit regressions; no market data is opened by these tests."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.fusion.quant import ShadowConfig
from core.strategy_lab import LabConfig, validate_bars
from scripts.validate_frozen_research import compact_result, digest, evaluate, load_manifest, write_new
from tests.test_fusion_quant import sample_bars


class FrozenAuditTests(unittest.TestCase):
    def test_existing_checkpoint_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.json"
            write_new(path, {"original": True})
            with self.assertRaises(FileExistsError):
                write_new(path, {"original": False})
            self.assertEqual(json.loads(path.read_text()), {"original": True})

    def test_changed_code_aborts_before_holdout_loader(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            freeze = root / "freeze.json"
            write_new(freeze, {"source_sha256": {"core/strategy_lab.py": "incorrect"}})
            write_new(freeze.with_suffix(".selections.json"), {"freeze_sha256": digest(freeze)})
            args = SimpleNamespace(output=root / "result.json", freeze=freeze, daily=root, intraday=root)
            with patch("scripts.validate_frozen_research.load_snapshot") as loader:
                with self.assertRaisesRegex(ValueError, "Frozen code changed"):
                    evaluate(args)
                loader.assert_not_called()
            self.assertFalse(args.output.exists())

    def test_dataset_without_permission_evidence_cannot_enter_commercial_protocol(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_new(root / "manifest.json", {"interval": "1d", "quote_currency": "USDT", "source": "Example provider"})
            with self.assertRaisesRegex(ValueError, "usage_rights"):
                load_manifest(root, "1d", "commercial_research")

    def test_personal_research_rights_are_not_treated_as_commercial_rights(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_new(root / "manifest.json", {"interval": "1d", "quote_currency": "USDT", "source": "Example provider",
                "usage_rights": {"basis": "Personal research only", "reference": "operator license record",
                                 "permitted_uses": ["personal_research"]}})
            self.assertEqual(load_manifest(root, "1d", "personal_research")["source"], "Example provider")
            with self.assertRaisesRegex(ValueError, "commercial_research"):
                load_manifest(root, "1d", "commercial_research")

    def test_test_start_excludes_all_training_equity_and_cost_stress_keeps_parameters(self):
        bars = validate_bars(sample_bars())
        cash = compact_result("synthetic-1d", "trend", bars, 100, LabConfig(), None)
        self.assertEqual(cash["summary"]["total_return"], 0)
        self.assertEqual(cash["test_start"], bars[100].timestamp.isoformat())
        self.assertEqual(cash["test_bars"], len(bars) - 100)
        self.assertEqual(cash["summary"]["total_trades"], 0)
        fusion = compact_result("synthetic-1d", "fusion", bars, 100, ShadowConfig())
        self.assertEqual(fusion["equity_curve"][0]["timestamp"], bars[100].timestamp.isoformat())
        self.assertTrue(all(row["entry_timestamp"] >= bars[100].timestamp.isoformat() for row in fusion["trades"]))
        self.assertEqual([row["cost_multiplier"] for row in fusion["cost_stress"]], [1, 2, 3])
        self.assertFalse(fusion["future_win_rate_guaranteed"])


if __name__ == "__main__":
    unittest.main()
