from __future__ import annotations

import json
from pathlib import Path

import neatlogs

from patient.config import (
    ESCALATE_ABOVE_PAISE,
    FAKE_TODAY,
    HISTORY_WINDOW,
    MAX_AGENT_TURNS,
    REFUND_WINDOW_DAYS,
)
from patient.tools import TOOL_SCHEMAS, dispatch
from patient.tools.ledger import Ledger, current_ledger, current_ticket
from patient.tracing import get_client

_ROOT = Path(__file__).resolve().parent
_SYSTEM_PATH = _ROOT / "prompts" / "system.md"
_POLICY_PATH = _ROOT / "policy" / "refund_policy.md"


def trim_history(messages: list[dict]) -> list[dict]:
    if HISTORY_WINDOW <= 0:
        return []
    return list(messages[-HISTORY_WINDOW:])


def build_system() -> str:
    header = (
        "OPERATIONAL SETTINGS\n"
        f"TODAY={FAKE_TODAY}\n"
        f"REFUND_WINDOW_DAYS={REFUND_WINDOW_DAYS}\n"
        f"ESCALATE_ABOVE_PAISE={ESCALATE_ABOVE_PAISE}\n\n"
    )
    body = _SYSTEM_PATH.read_text(encoding="utf-8")
    policy = _POLICY_PATH.read_text(encoding="utf-8")
    return header + body + "\n\n" + policy


def _create(client, messages: list[dict]):
    kwargs = {
        "model": _patient_model(),
        "temperature": 0,
        "messages": messages,
        "tools": TOOL_SCHEMAS,
        "tool_choice": "auto",
    }
    try:
        return client.chat.completions.create(**kwargs)
    except Exception as exc:
        text = str(exc).lower()
        if "temperature" not in text and "tool_choice" not in text:
            raise
        if "temperature" in text:
            kwargs.pop("temperature", None)
        if "tool_choice" in text:
            kwargs.pop("tool_choice", None)
        return client.chat.completions.create(**kwargs)


def _patient_model() -> str:
    import os

    from dotenv import load_dotenv

    load_dotenv()
    return os.environ.get("PATIENT_MODEL") or "gpt-5-mini"


def _assistant_dict(message) -> dict:
    payload = {"role": "assistant", "content": message.content or ""}
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.function.name,
                    "arguments": call.function.arguments or "{}",
                },
            }
            for call in message.tool_calls
        ]
    return payload


@neatlogs.span(kind="AGENT", name="kettle-support-agent")
def run_ticket(messages: list[dict], ledger: Ledger) -> str:
    token_ledger = current_ledger.set(ledger)
    token_ticket = current_ticket.set(ledger.ticket_id)
    try:
        client = get_client()
        system = build_system()
        history = [dict(message) for message in messages]
        for _turn in range(MAX_AGENT_TURNS):
            window = [{"role": "system", "content": system}, *trim_history(history)]
            response = _create(client, window)
            message = response.choices[0].message
            if not message.tool_calls:
                return (message.content or "").strip()
            history.append(_assistant_dict(message))
            for call in message.tool_calls:
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                    result = {"error": "invalid tool arguments"}
                    ledger.record(call.function.name, args, ok=False, error=result["error"], surfaced=True)
                else:
                    if not isinstance(args, dict):
                        args = {}
                    result = dispatch(call.function.name, args)
                history.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result),
                    }
                )
        return "I'm sorry, I could not finish this request. A human will follow up."
    finally:
        current_ledger.reset(token_ledger)
        current_ticket.reset(token_ticket)
