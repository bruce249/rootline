from __future__ import annotations

import asyncio
import json
import os

import neatlogs
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

URL = "https://ingest.neatlogs.com/mcp"


class NeatlogsMCPError(RuntimeError):
    """The MCP server answered with an error payload."""


async def _call(tool: str, args: dict) -> dict:
    load_dotenv()
    headers = {"Authorization": f"Bearer {os.environ['NEATLOGS_API_KEY']}"}
    async with create_mcp_http_client(headers=headers) as http_client:
        async with streamable_http_client(URL, http_client=http_client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool, args)
                parts = []
                for block in result.content:
                    text = getattr(block, "text", None)
                    if text:
                        parts.append(text)
                raw = "\n".join(parts).strip()
                if getattr(result, "is_error", False):
                    raise NeatlogsMCPError(f"{tool}: {raw[:500]}")
                if not raw:
                    return {}
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    return {"raw": raw}
                if isinstance(parsed, dict):
                    if parsed.get("errorCode") or (set(parsed) <= {"error", "errorCode"} and "error" in parsed):
                        raise NeatlogsMCPError(f"{tool}: {parsed.get('errorCode') or ''} {parsed.get('error')}".strip())
                    return parsed
                return {"data": parsed}


def _leaf(exc: BaseException) -> BaseException:
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return exc


@neatlogs.span(kind="MCP_TOOL", name="neatlogs_mcp")
def call(tool: str, args: dict) -> dict:
    try:
        return asyncio.run(_call(tool, args))
    except BaseExceptionGroup as group:
        # anyio task groups wrap the real error; surface it so retries and logs say what failed
        leaf = _leaf(group)
        if isinstance(leaf, NeatlogsMCPError):
            raise leaf from None
        raise NeatlogsMCPError(f"{tool}: {type(leaf).__name__}: {leaf}") from None


def _user_email() -> str:
    load_dotenv()
    email = os.environ.get("NEATLOGS_USER_EMAIL", "").strip()
    if not email:
        raise NeatlogsMCPError("NEATLOGS_USER_EMAIL is not set; triage writes need the team email")
    return email


def whoami() -> dict:
    return call("whoami", {})


def search_traces(
    query: str,
    limit: int = 50,
    offset: int = 0,
    workflow_name: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    detection_name: str | None = None,
    preview_chars: int = 600,
) -> dict:
    args: dict = {"query": query, "limit": limit, "offset": offset, "preview_chars": preview_chars}
    for key, value in (
        ("workflow_name", workflow_name),
        ("date_from", date_from),
        ("date_to", date_to),
        ("detection_name", detection_name),
    ):
        if value:
            args[key] = value
    return call("search_traces", args)


def get_trace_context(trace_id: str) -> dict:
    # Any span filter or clipping option makes this a "selective" request, which
    # the server currently rejects with not_enabled. Ask for the whole trace.
    return call("get_trace_context", {"trace_id": trace_id})


def list_detections(group_id: str | None = None) -> dict:
    return call("list_detections", {"group_id": group_id} if group_id else {})


def get_detection_trend(detection_name: str, period: str = "24h", granularity: str = "hour") -> dict:
    return call(
        "get_detection_trend",
        {"detection_name": detection_name, "period": period, "granularity": granularity},
    )


def list_detection_groups() -> dict:
    return call("list_detection_groups", {})


def preview_detection(kind: str, config: dict, run_on: dict | None = None, timeframe_days: int = 7) -> dict:
    args = {"type": kind, "config": config, "timeframe_days": timeframe_days, "limit": 10}
    if run_on:
        args["run_on"] = run_on
    return call("preview_detection", args)


def create_detection(
    display_name: str, group_id: str, kind: str, config: dict, description: str, run_on: dict | None = None
) -> dict:
    args = {
        "display_name": display_name,
        "group_id": group_id,
        "type": kind,
        "config": config,
        "description": description,
    }
    if run_on:
        args["run_on"] = run_on
    return call("create_detection", args)


def triage_list(status: str | None = None, severity: str | None = None) -> dict:
    args = {}
    if status:
        args["status"] = status
    if severity:
        args["severity"] = severity
    return call("triage_list", args)


def triage_get(triage_id: str) -> dict:
    return call("triage_get", {"triage_id": triage_id})


def triage_get_investigation(thread_id: str) -> dict:
    return call("triage_get_investigation", {"thread_id": thread_id})


def triage_accept(triage_id: str) -> dict:
    return call("triage_accept", {"triage_id": triage_id, "user_email": _user_email()})


def triage_update(triage_id: str, **fields) -> dict:
    return call("triage_update", {"triage_id": triage_id, "user_email": _user_email(), **fields})


def triage_update_status(triage_id: str, status: str, note: str) -> dict:
    return call(
        "triage_update_status",
        {"triage_id": triage_id, "user_email": _user_email(), "status": status, "resolution_note": note},
    )
