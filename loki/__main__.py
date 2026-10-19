"""
``python -m loki`` — start the paper-only TradingView webhook bot.

This is the container entrypoint referenced by ``Dockerfile`` (``CMD
["python", "-m", "loki"]``) and by ``deploy/`` systemd units. It boots the
Flask app from :class:`loki.bot.LokiBot`, which exposes:

    POST /webhook/tradingview   — authenticated TradingView alert -> paper order
    GET  /health                — liveness probe (used by the Docker HEALTHCHECK)

Configuration comes from ``LOKI_CONFIG`` (a YAML file such as
``config.loki.paper.yaml``), falling back to ``config.yaml``, then to safe
defaults. The host/port can be overridden with ``LOKI_HOST`` / ``LOKI_PORT``.
"""

from __future__ import annotations

import logging
import os

from loki.bot import LokiBot

logger = logging.getLogger("loki")


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    bot = LokiBot()
    host = os.environ.get("LOKI_HOST", "0.0.0.0")
    port = int(os.environ.get("LOKI_PORT", "8000"))
    logger.info("Starting Loki paper webhook bot on %s:%d", host, port)
    # threaded=True keeps the /health probe responsive while a webhook is
    # being validated/executed.
    bot.app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
