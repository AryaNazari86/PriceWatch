"""The one data type PriceWatch cares about: a watched Product.

No target price: a product is just tracked by URL, and any change in its
price vs. the last check (up or down) is flagged and emailed.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PricePoint(BaseModel):
    price: float
    currency: str
    in_stock: bool = True
    checked_at: datetime = Field(default_factory=_now)


class Product(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:10])
    url: str

    title: Optional[str] = None
    currency: str = "USD"
    current_price: Optional[float] = None
    in_stock: Optional[bool] = None

    price_history: list[PricePoint] = Field(default_factory=list)

    # Set by the most recent check only; reset to None when that check saw no
    # change. This is what makes the "changed" badge reflect the *last*
    # check's outcome rather than sticking forever.
    last_change_direction: Optional[Literal["up", "down"]] = None
    last_change_amount: Optional[float] = None

    last_checked: Optional[datetime] = None
    last_error: Optional[str] = None

    created_at: datetime = Field(default_factory=_now)

    @property
    def lowest_price(self) -> Optional[float]:
        prices = [p.price for p in self.price_history]
        return min(prices) if prices else None

    @property
    def is_lowest_ever(self) -> bool:
        if self.current_price is None or self.lowest_price is None:
            return False
        return self.current_price <= self.lowest_price

    @property
    def status(self) -> str:
        """One badge to summarize the product's state for the dashboard."""
        if self.current_price is None:
            return "error" if self.last_error else "pending"
        if self.last_change_direction == "down":
            return "dropped"
        if self.last_change_direction == "up":
            return "increased"
        if self.is_lowest_ever:
            return "lowest"
        return "watching"

    def public_dict(self) -> dict:
        """Serialize including the computed fields the frontend needs."""
        data = self.model_dump(mode="json")
        data["lowest_price"] = self.lowest_price
        data["is_lowest_ever"] = self.is_lowest_ever
        data["status"] = self.status
        return data
