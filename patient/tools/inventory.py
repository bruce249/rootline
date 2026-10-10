from __future__ import annotations

import hashlib

import neatlogs

from patient.config import INVENTORY_RETRIES
from patient.tools.ledger import current_ledger, current_ticket


def should_timeout(ticket_id: str, sku: str, attempt: int) -> bool:
    """Deterministic stand-in for hash(ticket_id + sku + attempt) % 5 == 0.

    CPython salts the builtin hash per process, so a sha256 of the same string
    is used. The failure rule is unchanged: timeout when the digest mod 5 is 0.
    """
    raw = f"{ticket_id}{sku}{attempt}".encode()
    return int(hashlib.sha256(raw).hexdigest(), 16) % 5 == 0


def _units(sku: str) -> int:
    return 5 + (sum(sku.encode()) % 15)


@neatlogs.span(kind="TOOL", tool_name="check_inventory")
def check_inventory(sku: str) -> dict:
    ticket_id = current_ticket.get() or ""
    ledger = current_ledger.get()
    last_error = "TimeoutError"
    for attempt in range(INVENTORY_RETRIES + 1):
        if should_timeout(ticket_id, sku, attempt):
            if attempt < INVENTORY_RETRIES and ledger is not None:
                ledger.record(
                    "check_inventory",
                    {"sku": sku, "attempt": attempt},
                    ok=False,
                    error="TimeoutError",
                    surfaced=False,
                )
                continue
            raise TimeoutError(last_error)
        return {"sku": sku, "in_stock": True, "units": _units(sku)}
    raise TimeoutError(last_error)
