"""Train a reproducible, account-free historical market research model.

Use --public for the CC BY benchmark or --csv for up to 250000 dated returns
(date,CMKT). Outputs are new JSON files, never executable pickle objects. A local
CSV needs its own usage rights; this script does not acquire those rights.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.fusion.history import parse_factor_csv, public_history
from core.fusion.learning import SPEC, train_research
import hashlib
from datetime import datetime, timezone


def write_new(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--public", action="store_true")
    group.add_argument("--csv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    snapshot = args.output.with_suffix(".data.json")
    protocol = args.output.with_suffix(".protocol.json")
    if any(path.exists() for path in (args.output, snapshot, protocol)):
        parser.error("Output exists; choose a new filename to preserve the experiment history")
    if args.public:
        dataset = public_history()
    else:
        if args.csv.stat().st_size > 100_000_000:
            parser.error("CSV exceeds 100 MB")
        dataset = {
            "observations": parse_factor_csv(args.csv.read_text(encoding="utf-8-sig")),
            "source": {"name": "Operator-supplied return CSV; rights and provenance unverified"},
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_new(snapshot, dataset)
    root = Path(__file__).resolve().parents[1]
    write_new(
        protocol,
        {
            "recorded_before_model_evaluation_utc": datetime.now(timezone.utc).isoformat(),
            "specification": SPEC,
            "snapshot_sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
            "code_sha256": {
                name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                for name in (
                    "core/fusion/learning.py",
                    "core/fusion/history.py",
                    "scripts/train_market_research.py",
                )
            },
            "limitation": "Local record of a fixed experiment, not proof that upstream history or its design was previously unseen.",
        },
    )
    report = train_research(dataset["observations"], source=dataset["source"])
    write_new(args.output, report)
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "observations",
                    "training",
                    "validation",
                    "test",
                    "status",
                    "target_70_percent_proven",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
