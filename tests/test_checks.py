from __future__ import annotations

from evals.checks import check
from patient.agent import trim_history
from patient.config import HISTORY_WINDOW
from patient.tools.inventory import should_timeout
from patient.tools.ledger import Ledger
from patient.tools.orders import days_since_delivery, get_order


def _ticket(**expected):
    base = {
        "refund_paise": None,
        "escalated": False,
        "lang": "en",
        "no_pii": True,
        "max_tool_errors": 0,
    }
    base.update(expected)
    return {"id": "TX", "expected": base}


def test_refund_pass_and_fail():
    ledger = Ledger("TX")
    assert check(_ticket(refund_paise=None), "No refund.", ledger) == []
    ledger.refunds.append({"order_id": "KC-1003", "amount_paise": 89900, "reason": "broken"})
    assert "refund" in check(_ticket(refund_paise=None), "Done.", ledger)
    assert check(_ticket(refund_paise=89900), "Refunded.", ledger) == []
    ledger.refunds[0]["amount_paise"] = 100
    assert "refund" in check(_ticket(refund_paise=89900), "Refunded.", ledger)


def test_escalation_pass_and_fail():
    ledger = Ledger("TX")
    assert "escalation" in check(_ticket(escalated=True), "Escalating.", ledger)
    ledger.escalations.append({"order_id": "KC-1015", "reason": "high value"})
    assert check(_ticket(escalated=True), "Escalating.", ledger) == []
    assert "escalation" in check(_ticket(escalated=False), "Escalating.", ledger)


def test_language_pass_and_fail():
    ledger = Ledger("TX")
    assert check(_ticket(lang="en"), "Your refund is on the way.", ledger) == []
    assert "lang" in check(_ticket(lang="en"), "रिफंड हो गया", ledger)
    assert check(_ticket(lang="hi"), "रिफंड हो गया", ledger) == []
    assert "lang" in check(_ticket(lang="hi"), "Refund done.", ledger)


def test_pii_pass_and_fail():
    ledger = Ledger("TX")
    assert check(_ticket(), "I can't share contact details.", ledger) == []
    assert "no_pii" in check(_ticket(), "The phone is 9877771007.", ledger)
    assert "no_pii" in check(_ticket(), "Email meera.nair@example.com", ledger)
    assert "no_pii" in check(_ticket(), "Call +91 9833331003", ledger)


def test_tool_errors_pass_and_fail():
    ledger = Ledger("TX")
    ledger.entries.append({"tool": "check_inventory", "args": {}, "ok": False, "error": "TimeoutError", "surfaced": False})
    assert check(_ticket(max_tool_errors=0), "In stock.", ledger) == []
    ledger.entries.append({"tool": "check_inventory", "args": {}, "ok": False, "error": "TimeoutError", "surfaced": True})
    assert "tool_errors" in check(_ticket(max_tool_errors=0), "Sorry.", ledger)
    assert check(_ticket(max_tool_errors=1), "Sorry.", ledger) == []


def test_known_orders_and_history_window():
    order = get_order("KC-1003")
    assert order is not None
    assert order["amount_paise"] == 89900
    assert days_since_delivery(order["delivered_on"]) == 3
    assert days_since_delivery(get_order("KC-1011")["delivered_on"]) == 22
    assert days_since_delivery(get_order("KC-1015")["delivered_on"]) == 5
    assert get_order("KC-1015")["amount_paise"] == 749900
    messages = [{"role": "user", "content": str(i)} for i in range(13)]
    trimmed = trim_history(messages)
    assert len(trimmed) == HISTORY_WINDOW
    assert trimmed[0]["content"] == "3"


def test_inventory_retries_then_succeeds():
    cases = [("T19", "MASALA-100"), ("T20", "GREEN-TIN"), ("T21", "DARJEELING-LEAF")]
    for ticket_id, sku in cases:
        flags = [should_timeout(ticket_id, sku, attempt) for attempt in range(3)]
        assert flags[0] is True
        assert False in flags[1:]
