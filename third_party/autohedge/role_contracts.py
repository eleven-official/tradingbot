"""Structured role contracts adapted from AutoHedge workers.py and prompts.py.

Copyright (c) 2023 Eternal Reclaimer. MIT; see adjacent LICENSE.
Original sources are retained in upstream/. These contracts preserve AutoHedge's
director -> quant/sentiment -> risk -> execution division of responsibilities.
Loki supplies deterministic evidence and proposals; no Swarms agents, model
providers, search tools, credentials, or execution transports are initialized.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

ROLE_CONTRACTS = {
    "director": {"title": "Trading Director", "inputs": ["task", "symbol", "market_data"],
                 "outputs": ["thesis", "key_factors", "risks", "decision"]},
    "quant": {"title": "Quant Analyst", "inputs": ["symbol", "thesis", "market_data"],
              "outputs": ["technical_score", "volume_score", "trend_strength", "volatility", "key_levels"]},
    "sentiment": {"title": "Sentiment Analyst", "inputs": ["symbol", "news", "timeframe"],
                  "outputs": ["sentiment", "themes", "critical_events", "limitations"]},
    "risk": {"title": "Risk Manager", "inputs": ["symbol", "thesis", "quant_analysis", "portfolio"],
             "outputs": ["position_size", "drawdown_risk", "market_exposure", "risk_checks"]},
    "execution": {"title": "Execution Planner", "inputs": ["symbol", "thesis", "risk_assessment"],
                  "outputs": ["quantity", "entry", "stop_loss", "take_profit", "time_in_force"]},
}


def role_packet(role: str, *, symbol: str, evidence: dict[str, Any]) -> dict[str, Any]:
    """Return a data-only packet for an auditable stage of the council pipeline."""
    if role not in ROLE_CONTRACTS:
        raise ValueError("Unknown council role")
    return {"role": role, "symbol": symbol, "contract": deepcopy(ROLE_CONTRACTS[role]),
            "evidence": deepcopy(evidence), "engine": "deterministic_role_pipeline"}
