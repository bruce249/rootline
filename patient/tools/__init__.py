from __future__ import annotations

from patient.tools.escalate import escalate
from patient.tools.inventory import check_inventory
from patient.tools.ledger import current_ledger
from patient.tools.orders import lookup_order
from patient.tools.refunds import issue_refund

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "description": "Look up one order by its id, copied from the customer messages.",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_inventory",
            "description": "Check whether a sku is in stock. Retries internally on timeout.",
            "parameters": {
                "type": "object",
                "properties": {"sku": {"type": "string"}},
                "required": ["sku"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "issue_refund",
            "description": "Record a refund for the full amount in paise. Does not check the refund window or the escalation limit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "amount_paise": {"type": "integer"},
                    "reason": {"type": "string"},
                },
                "required": ["order_id", "amount_paise", "reason"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate",
            "description": "Send an order to a human. Use this instead of issue_refund when the amount must be escalated.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["order_id", "reason"],
                "additionalProperties": False,
            },
        },
    },
]

_TOOLS = {
    "lookup_order": lookup_order,
    "check_inventory": check_inventory,
    "issue_refund": issue_refund,
    "escalate": escalate,
}


def dispatch(name: str, args: dict) -> dict:
    ledger = current_ledger.get()
    fn = _TOOLS.get(name)
    if fn is None:
        error = f"unknown tool: {name}"
        if ledger is not None:
            ledger.record(name, args, ok=False, error=error, surfaced=True)
        return {"error": error}
    try:
        result = fn(**args)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        if ledger is not None:
            ledger.record(name, args, ok=False, error=error, surfaced=True)
        return {"error": error}
    if ledger is not None:
        ledger.record(name, args, ok=True, error=None, surfaced=True)
    return result
