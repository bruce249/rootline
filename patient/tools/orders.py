from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

import neatlogs

from patient.config import FAKE_TODAY

_ORDERS_PATH = Path(__file__).resolve().parents[1] / "data" / "orders.json"


@lru_cache(maxsize=1)
def load_orders() -> list[dict]:
    return json.loads(_ORDERS_PATH.read_text(encoding="utf-8"))


def days_since_delivery(delivered_on: str) -> int:
    return (date.fromisoformat(FAKE_TODAY) - date.fromisoformat(delivered_on)).days


def get_order(order_id: str) -> dict | None:
    for order in load_orders():
        if order["order_id"] == order_id:
            return order
    return None


@neatlogs.span(kind="TOOL", tool_name="lookup_order")
def lookup_order(order_id: str) -> dict:
    order = get_order(order_id)
    if order is None:
        raise KeyError(f"order not found: {order_id}")
    payload = dict(order)
    payload["days_since_delivery"] = days_since_delivery(order["delivered_on"])
    return payload
