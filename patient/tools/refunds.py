from __future__ import annotations

import neatlogs

from patient.tools.ledger import current_ledger
from patient.tools.orders import get_order


@neatlogs.span(kind="TOOL", tool_name="issue_refund")
def issue_refund(order_id: str, amount_paise: int, reason: str) -> dict:
    order = get_order(order_id)
    if order is None:
        raise KeyError(f"order not found: {order_id}")
    amount = int(amount_paise)
    record = {"order_id": order_id, "amount_paise": amount, "reason": reason}
    ledger = current_ledger.get()
    if ledger is not None:
        ledger.refunds.append(record)
    return {"ok": True, "refund": record}
