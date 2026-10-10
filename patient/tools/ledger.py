from __future__ import annotations

from contextvars import ContextVar
from typing import Any


class Ledger:
    def __init__(self, ticket_id: str):
        self.ticket_id = ticket_id
        self.entries: list[dict[str, Any]] = []
        self.refunds: list[dict[str, Any]] = []
        self.escalations: list[dict[str, Any]] = []

    def record(self, tool: str, args: dict, ok: bool, error: str | None = None, surfaced: bool = True) -> None:
        self.entries.append(
            {
                "tool": tool,
                "args": args,
                "ok": ok,
                "error": error,
                "surfaced": surfaced,
            }
        )

    def __repr__(self) -> str:
        return f"Ledger(ticket_id={self.ticket_id!r})"


current_ledger: ContextVar[Ledger | None] = ContextVar("current_ledger", default=None)
current_ticket: ContextVar[str | None] = ContextVar("current_ticket", default=None)
