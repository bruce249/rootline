from __future__ import annotations

import json
from pathlib import Path

import neatlogs

from evals.checks import check
from patient.agent import run_ticket
from patient.tools.ledger import Ledger

_TICKETS_PATH = Path(__file__).resolve().parent / "tickets.json"


def load_tickets() -> dict[str, dict]:
    rows = json.loads(_TICKETS_PATH.read_text(encoding="utf-8"))
    return {row["id"]: row for row in rows}


TICKETS = load_tickets()


class EvalCheckFailed(Exception):
    def __init__(self, message: str, failed: list[str], reply: str, ledger: Ledger):
        super().__init__(message)
        self.failed = failed
        self.reply = reply
        self.ledger = ledger


@neatlogs.span(kind="TOOL", tool_name="eval_check")
def eval_check(ticket_id: str, git_sha: str, run_label: str, failed_checks: list[str]) -> dict:
    """Record the verdict as its own span so investigators can read it from the trace."""
    return {
        "ticket_id": ticket_id,
        "git_sha": git_sha,
        "run_label": run_label,
        "passed": not failed_checks,
        "failed_checks": failed_checks,
    }


@neatlogs.span(kind="WORKFLOW", name="support-ticket")
def handle_ticket(ticket_id: str, git_sha: str, run_label: str, messages: list) -> dict:
    ledger = Ledger(ticket_id)
    reply = run_ticket(messages, ledger)
    failed = check(TICKETS[ticket_id], reply, ledger)
    eval_check(ticket_id, git_sha, run_label, failed)
    if failed:
        short = git_sha[:7] if git_sha and git_sha != "unknown" else git_sha
        raise EvalCheckFailed(
            f"ticket={ticket_id} sha={short} failed_checks={failed}",
            failed,
            reply,
            ledger,
        )
    return {
        "ticket_id": ticket_id,
        "git_sha": git_sha,
        "run_label": run_label,
        "passed": True,
        "reply": reply,
        "refunds": ledger.refunds,
        "escalations": ledger.escalations,
    }


def run_one(ticket_id: str, run_label: str, git_sha: str) -> dict:
    ticket = TICKETS[ticket_id]
    try:
        result = handle_ticket(ticket_id, git_sha, run_label, ticket["messages"])
        result["failed_checks"] = []
        return result
    except EvalCheckFailed as exc:
        return {
            "ticket_id": ticket_id,
            "git_sha": git_sha,
            "run_label": run_label,
            "passed": False,
            "failed_checks": exc.failed,
            "reply": exc.reply,
            "error": str(exc),
            "refunds": exc.ledger.refunds,
            "escalations": exc.ledger.escalations,
        }
