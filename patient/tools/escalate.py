from __future__ import annotations

import neatlogs

from patient.tools.ledger import current_ledger
from patient.tools.orders import get_order


@neatlogs.span(kind="TOOL", tool_name="escalate")
def escalate(order_id: str, reason: str) -> dict:
    order = get_order(order_id)
    if order is None:
        raise KeyError(f"order not found: {order_id}")
    record = {"order_id": order_id, "reason": reason}
    ledger = current_ledger.get()
    if ledger is not None:
        ledger.escalations.append(record)
    return {"ok": True, "escalation": record}
