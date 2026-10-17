"""Selected MIT originals and their attribution must survive packaging edits."""
import hashlib
import json
from pathlib import Path
import unittest


class FusionProvenanceTests(unittest.TestCase):
    def test_original_sources_match_recorded_hashes_and_licenses_are_retained(self):
        root = Path(__file__).resolve().parents[1] / "third_party"
        for project in ("vibe_trading", "autohedge"):
            with self.subTest(project=project):
                directory = root / project
                provenance = json.loads((directory / "PROVENANCE.json").read_text(encoding="utf-8"))
                license_text = (directory / "LICENSE").read_text(encoding="utf-8")
                self.assertIn("MIT License", license_text)
                self.assertIn("Copyright", license_text)
                self.assertIn("Permission is hereby granted", license_text)
                self.assertEqual(provenance["license"], "MIT")
                for source in provenance["selected_sources"]:
                    data = (directory / source["retained_original"]).read_bytes()
                    self.assertEqual(hashlib.sha256(data).hexdigest(), source["original_sha256"])
                    self.assertTrue((directory / source["runtime_adaptation"]).is_file())
        self.assertIn("HKUDS", (root / "vibe_trading/NOTICE").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
