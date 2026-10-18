"""Launch the unified local Loki workspace without enabling real trading."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def configure(config_path: Path | None = None):
    """Load a local, ignored engine configuration; never accept it from HTTP."""
    config = {}
    config_directory = None
    if config_path is not None:
        config_path = config_path.resolve()
        config_directory = config_path.parent
        raw = config_path.read_text(encoding="utf-8-sig")
        if len(raw) > 32000:
            raise ValueError("Local engine settings are too large")
        config = json.loads(raw)
        if not isinstance(config, dict):
            raise ValueError("Local engine settings must be a JSON object")
    allowed = {
        "fincept_path",
        "fincept_python",
        "fincept_license_confirmed",
        "fincept_allow_analytics",
        "mirofish_url",
        "mirofish_allow_jobs",
        "mirofish_data_path",
    }
    if set(config) - allowed:
        raise ValueError("Unknown local engine setting")
    updates = {}
    for field, variable in (
        ("fincept_path", "LOKI_FINCEPT_PATH"),
        ("fincept_python", "LOKI_FINCEPT_PYTHON"),
        ("mirofish_url", "LOKI_MIROFISH_URL"),
        ("mirofish_data_path", "LOKI_MIROFISH_DATA_PATH"),
    ):
        if field in config:
            if not isinstance(config[field], str) or len(config[field]) > 4096:
                raise ValueError(f"{field} must be a bounded local path or URL")
            value = config[field]
            if "\x00" in value:
                raise ValueError(f"{field} contains an invalid null character")
            if (
                field in {"fincept_path", "fincept_python", "mirofish_data_path"}
                and value
                and config_directory is not None
            ):
                location = Path(value).expanduser()
                value = str(location if location.is_absolute() else config_directory / location)
            updates[variable] = value
    for field, variable in (
        ("fincept_license_confirmed", "LOKI_FINCEPT_LICENSE_CONFIRMED"),
        ("fincept_allow_analytics", "LOKI_FINCEPT_ALLOW_ANALYTICS"),
        ("mirofish_allow_jobs", "LOKI_MIROFISH_ALLOW_JOBS"),
    ):
        if field in config:
            if not isinstance(config[field], bool):
                raise ValueError(f"{field} must be true or false")
            updates[variable] = "1" if config[field] else "0"
    # Validate everything before changing a process-level enablement flag. A
    # rejected configuration must not leave a partly enabled native engine.
    from core.fusion.external import FinceptAdapter, MiroFishAdapter

    candidate = dict(os.environ, **updates)
    FinceptAdapter.from_env(candidate)
    MiroFishAdapter.from_env(candidate)
    updates["LOKI_FUSION_LOCAL"] = "1"
    os.environ.update(updates)
    return config


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Local JSON engine settings, stored outside version control",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate configuration and imports without starting a server",
    )
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        parser.error("Choose a port between 1024 and 65535")
    try:
        configure(args.config)
        from core.fusion.external import FinceptAdapter, MiroFishAdapter
        from core.fusion.quant import analyze_factors
        from core.fusion.council import build_council_report
        from main import app

        FinceptAdapter.from_env()
        MiroFishAdapter.from_env()
    except (OSError, ValueError, ImportError) as exc:
        parser.error(str(exc))
    if args.check:
        print(
            "Loki Fusion configuration and application imports are valid. No engines or trading were started."
        )
        return 0
    import uvicorn

    print(f"Loki Fusion: http://127.0.0.1:{args.port} — paper and research only")
    uvicorn.run(app, host="127.0.0.1", port=args.port, proxy_headers=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
