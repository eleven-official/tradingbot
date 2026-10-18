"""Original Vibe-Trading order contract, MIT; see LICENSE and PROVENANCE.json.

Only imports were narrowed; the PendingOrderRequest class is unchanged.
"""

from __future__ import annotations
import math
from typing import Literal, Self
from pydantic import BaseModel, ConfigDict, Field, model_validator


class PendingOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    symbol: str = Field(min_length=1)
    side: Literal["buy", "sell"]
    quantity: float | int | None
    notional: float | int | None
    order_type: Literal["market", "limit"]
    limit_price: float | int | None
    time_in_force: Literal["day", "gtc"]

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if (self.quantity is None) == (self.notional is None):
            raise ValueError("exactly one order size is required")
        for value in (self.quantity, self.notional, self.limit_price):
            if value is not None and (not math.isfinite(value) or value <= 0):
                raise ValueError("order numerics must be finite and positive")
        if (self.order_type == "limit") != (self.limit_price is not None):
            raise ValueError("limit price must match the order type")
        return self
