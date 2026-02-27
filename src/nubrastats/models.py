from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Trade:
    timestamp: datetime
    symbol: str
    side: str
    quantity: float
    price: float
    fee: float = 0.0
    strategy_id: str | None = None
    tag: str | None = None


@dataclass(slots=True)
class OrderEvent:
    timestamp: datetime
    order_id: str | int
    symbol: str
    side: str
    quantity: float
    price: float
    status: str
    tag: str | None = None

