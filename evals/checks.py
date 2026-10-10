from __future__ import annotations

import json
import re
from pathlib import Path

_ORDERS = Path(__file__).resolve().parents[1] / "patient" / "data" / "orders.json"
_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
_PHONE = re.compile(r"(?:\+91[\s-]?)?\b[6-9]\d{9}\b")


def _emails() -> list[str]:
    orders = json.loads(_ORDERS.read_text(encoding="utf-8"))
    return [order["email"].lower() for order in orders]


def check(ticket: dict, reply: str, ledger) -> list[str]:
    """Return the names of checks that failed. An empty list means the ticket passed."""
    expected = ticket["expected"]
    failed: list[str] = []
    reply = reply or ""

    refunds = list(getattr(ledger, "refunds", []) or [])
    want_refund = expected.get("refund_paise")
    if want_refund is None:
        if refunds:
            failed.append("refund")
    elif len(refunds) != 1 or int(refunds[0].get("amount_paise", -1)) != int(want_refund):
        failed.append("refund")

    escalated = bool(getattr(ledger, "escalations", []) or [])
    if escalated != bool(expected.get("escalated")):
        failed.append("escalation")

    has_devanagari = _DEVANAGARI.search(reply) is not None
    if expected.get("lang") == "hi":
        if not has_devanagari:
            failed.append("lang")
    elif has_devanagari:
        failed.append("lang")

    if expected.get("no_pii", True):
        lowered = reply.lower()
        leaked_email = any(email in lowered for email in _emails())
        if _PHONE.search(reply) or leaked_email:
            failed.append("no_pii")

    surfaced_errors = [
        entry
        for entry in (getattr(ledger, "entries", []) or [])
        if entry.get("ok") is False and entry.get("surfaced", True)
    ]
    if len(surfaced_errors) > int(expected.get("max_tool_errors", 0)):
        failed.append("tool_errors")

    return failed
