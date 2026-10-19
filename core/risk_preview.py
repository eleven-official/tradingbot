"""Read-only position sizing using a cash budget and explicit trading costs."""
from math import isfinite


def preview_position(equity, entry, stop, risk_pct=0.5, max_exposure_pct=20,
                     fee_bps=10, slippage_bps=5):
    values = (equity, entry, stop, risk_pct, max_exposure_pct, fee_bps, slippage_bps)
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or
           not isfinite(value) for value in values):
        raise ValueError("All sizing inputs must be finite numbers")
    if not equity > 0 or not entry > stop > 0:
        raise ValueError("For a long position, equity > 0 and entry > stop > 0 are required")
    if not 0 < risk_pct <= 5 or not 0 < max_exposure_pct <= 100:
        raise ValueError("Risk must be above 0 and at most 5%; exposure at most 100%")
    if not 0 <= fee_bps <= 1000 or not 0 <= slippage_bps <= 1000:
        raise ValueError("Fees and slippage must be between 0 and 1000 basis points")
    fee = fee_bps / 10000
    slip = slippage_bps / 10000
    buy = entry * (1 + slip)
    sell = stop * (1 - slip)
    risk_per_unit = buy * (1 + fee) - sell * (1 - fee)
    if not isfinite(risk_per_unit) or risk_per_unit <= 0:
        raise ValueError("Price distance is too extreme for reliable sizing")
    risk_budget = equity * risk_pct / 100
    exposure_budget = equity * max_exposure_pct / 100
    quantity = min(risk_budget / risk_per_unit, exposure_budget / (buy * (1 + fee)))
    result = {
        "quantity": quantity,
        "notional": quantity * entry,
        "cash_required": quantity * buy * (1 + fee),
        "planned_loss_at_stop": quantity * risk_per_unit,
        "risk_budget": risk_budget,
        "binding_limit": "exposure" if quantity < risk_budget / risk_per_unit else "risk",
        "mode": "preview_only",
        "assumptions": ["Long-only cash position; no leverage", "Fees and slippage on entry and exit",
                        "A price gap through the stop can increase the actual loss",
                        "Existing portfolio exposure and exchange lot sizes are not included"],
    }
    if any(not isfinite(result[key]) for key in
           ("quantity", "notional", "cash_required", "planned_loss_at_stop", "risk_budget")):
        raise ValueError("Inputs are too extreme for reliable sizing")
    return result
