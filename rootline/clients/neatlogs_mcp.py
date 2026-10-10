from __future__ import annotations

import asyncio
import json
import os

import neatlogs
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = "https://ingest.neatlogs.com/mcp"


async def _call(tool: str, args: dict) -> dict:
    load_dotenv()
    headers = {"Authorization": f"Bearer {os.environ['NEATLOGS_API_KEY']}"}
    async with streamablehttp_client(URL, headers=headers) as (read, write, _session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, args)
            parts = []
            for block in result.content:
                text = getattr(block, "text", None)
                if text:
                    parts.append(text)
            raw = "\n".join(parts).strip()
            if not raw:
                return {}
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return {"raw": raw}
            if isinstance(parsed, dict):
                return parsed
            return {"data": parsed}


@neatlogs.span(kind="MCP_TOOL", name="neatlogs_mcp")
def call(tool: str, args: dict) -> dict:
    return asyncio.run(_call(tool, args))


def search_traces(query: str, limit: int = 50, offset: int = 0, filters: dict | None = None) -> dict:
    return call(
        "search_traces",
        {"query": query, "limit": limit, "offset": offset, "filters": filters or {}},
    )


def get_trace_context(trace_id: str) -> dict:
    return call("get_trace_context", {"trace_id": trace_id})


def list_detections(limit: int = 50) -> dict:
    return call("list_detections", {"limit": limit})


def get_detection_trend(detection_name: str, granularity: str = "hour", date_range: str = "last_24h") -> dict:
    return call(
        "get_detection_trend",
        {"detection_name": detection_name, "granularity": granularity, "date_range": date_range},
    )


def triage_list(status: str | None = None, severity: str | None = None) -> dict:
    args = {}
    if status:
        args["status"] = status
    if severity:
        args["severity"] = severity
    return call("triage_list", args)


def triage_get(fix_id: str) -> dict:
    return call("triage_get", {"fix_id": fix_id})


def triage_get_investigation(fix_id: str) -> dict:
    return call("triage_get_investigation", {"fix_id": fix_id})


def triage_accept(fix_id: str) -> dict:
    return call("triage_accept", {"fix_id": fix_id})


def triage_update_status(fix_id: str, status: str, note: str) -> dict:
    return call("triage_update_status", {"fix_id": fix_id, "status": status, "note": note})
