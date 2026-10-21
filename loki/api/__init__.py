"""Loki's public API package.

The web application is imported lazily so pure calculation helpers remain
usable in minimal Python environments.
"""

from typing import Any

__all__ = ["app"]


def __getattr__(name: str) -> Any:
    if name == "app":
        from loki.api.server import app

        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

