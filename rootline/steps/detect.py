from __future__ import annotations

import ast
import json
import re

import neatlogs

from rootline.clients.external import call_external
from rootline.clients.llm import complete
from rootline.clients.neatlogs_mcp import (
    get_detection_trend,
    get_trace_context,
    list_detections,
    search_traces,
    triage_get,
    triage_get_investigation,
    triage_list,
)

_TICKET = re.compile(r"ticket=([A-Za-z0-9_-]+)")
_SHA = re.compile(r"sha=([0-9a-fA-F]+)")
_CHECKS = re.compile(r"failed_checks=(\[[^\]]*\])")


def _rows(payload: dict, key: str) -> list:
    if not isinstance(payload, dict):
        return []
    value = payload.get(key)
    if isinstance(value, list):
        return value
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get(key), list):
        return data[key]
    if isinstance(data, list):
        return data
    return []


def _as_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _deepest_error(span: dict) -> dict | None:
    best = None
    best_depth = -1

    def walk(node, depth: int) -> None:
        nonlocal best, best_depth
        if not isinstance(node, dict):
            return
        if str(node.get("status", "")).lower() in {"error", "failed"} and depth >= best_depth:
            best = node
            best_depth = depth
        for child in node.get("children") or []:
            walk(child, depth + 1)

    walk(span, 0)
    return best


def _extract(trace: dict, context: dict) -> dict:
    root = _as_dict(context.get("root_span"))
    raw_input = root.get("input")
    if isinstance(raw_input, str):
        raw_input = _as_dict(raw_input)
    raw_input = raw_input if isinstance(raw_input, dict) else {}
    error_message = str(root.get("error") or root.get("error_message") or trace.get("error_message") or "")
    ticket_match = _TICKET.search(error_message)
    sha_match = _SHA.search(error_message)
    checks_match = _CHECKS.search(error_message)
    failed_checks = raw_input.get("failed_checks")
    if checks_match:
        try:
            failed_checks = ast.literal_eval(checks_match.group(1))
        except (SyntaxError, ValueError):
            failed_checks = []
    deepest = _deepest_error(root)
    return {
        "trace_id": trace.get("trace_id"),
        "url": trace.get("url"),
        "ticket_id": raw_input.get("ticket_id") or (ticket_match.group(1) if ticket_match else None),
        "git_sha": raw_input.get("git_sha") or (sha_match.group(1) if sha_match else None),
        "failed_checks": failed_checks or [],
        "error_message": error_message,
        "deepest": {
            "name": (deepest or {}).get("name"),
            "tool_name": (deepest or {}).get("tool_name"),
            "input": (deepest or {}).get("input"),
            "output": (deepest or {}).get("output"),
        }
        if deepest
        else None,
    }


def _signature(evidence: list[dict]) -> str:
    checks = []
    for item in evidence:
        for name in item.get("failed_checks") or []:
            if name not in checks:
                checks.append(name)
    observed = ", ".join(checks) or "unknown"
    prompt = (
        "Write one plain sentence describing the production failure, using only this evidence. "
        f"Failed checks: {observed}. Evidence JSON follows.\n{json.dumps(evidence)[:6000]}"
    )
    try:
        text = complete("You write one factual sentence and nothing else.", prompt)
        return text.splitlines()[0].strip() or f"Failing checks observed: {observed}."
    except Exception:
        return f"Failing checks observed: {observed}."


@neatlogs.span(kind="AGENT", name="detect")
def run(state: dict) -> dict:
    since = state.get("since") or "last_24h"
    found = call_external(
        state,
        "DETECT",
        lambda: search_traces(
            "support-ticket",
            limit=50,
            filters={"status": "error", "date_range": since},
        ),
    )
    traces = _rows(found, "traces")[:5]
    failing = []
    for trace in traces:
        trace_id = trace.get("trace_id")
        if not trace_id:
            continue
        context = call_external(state, "DETECT", lambda tid=trace_id: get_trace_context(tid))
        failing.append(_extract(trace, context))

    detections = []
    try:
        listed = call_external(state, "DETECT", lambda: list_detections(limit=50))
        for detection in _rows(listed, "detections"):
            if not detection.get("fire_count_24h"):
                continue
            name = detection.get("name")
            trend = call_external(
                state,
                "DETECT",
                lambda detection_name=name: get_detection_trend(detection_name),
            )
            detections.append({"detection": detection, "trend": trend})
    except Exception as exc:
        state["errors"].append({"step": "DETECT", "error": f"detections: {exc}", "at": state.get("updated_at")})

    second_opinion = None
    try:
        drafts = call_external(state, "DETECT", lambda: triage_list(status="draft"))
        our_ids = {item.get("trace_id") for item in failing if item.get("trace_id")}
        opinions = []
        for fix in _rows(drafts, "fixes"):
            linked = set(fix.get("linked_traces") or [])
            if our_ids and linked and not (linked & our_ids):
                continue
            fix_id = str(fix.get("id") or "")
            if not fix_id:
                continue
            opinions.append(
                {
                    "fix": call_external(state, "DETECT", lambda fid=fix_id: triage_get(fid)),
                    "investigation": call_external(
                        state, "DETECT", lambda fid=fix_id: triage_get_investigation(fid)
                    ),
                }
            )
        second_opinion = opinions or None
    except Exception as exc:
        state["errors"].append({"step": "DETECT", "error": f"triage: {exc}", "at": state.get("updated_at")})

    last_good = None
    try:
        successes = call_external(
            state,
            "DETECT",
            lambda: search_traces("support-ticket", limit=20, filters={"status": "success", "date_range": since}),
        )
        wanted = {item.get("ticket_id") for item in failing}
        for trace in _rows(successes, "traces"):
            trace_id = trace.get("trace_id")
            if not trace_id:
                continue
            context = call_external(state, "DETECT", lambda tid=trace_id: get_trace_context(tid))
            extracted = _extract(trace, context)
            if extracted.get("git_sha") and (not wanted or extracted.get("ticket_id") in wanted):
                last_good = extracted["git_sha"]
                break
    except Exception as exc:
        state["errors"].append({"step": "DETECT", "error": f"last_good: {exc}", "at": state.get("updated_at")})

    bad_shas = []
    for item in failing:
        sha = item.get("git_sha")
        if sha and sha not in bad_shas:
            bad_shas.append(sha)
    return {
        "failing_traces": failing,
        "failure_signature": _signature(failing),
        "bad_shas": bad_shas,
        "last_good_sha": last_good,
        "detections": detections,
        "second_opinion": second_opinion,
    }
