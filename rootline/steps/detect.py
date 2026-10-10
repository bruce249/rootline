from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

import neatlogs

from rootline.clients.external import call_external
from rootline.clients.git import git
from rootline.clients.llm import complete
from rootline.clients.neatlogs_mcp import (
    get_detection_trend,
    get_trace_context,
    list_detections,
    search_traces,
    triage_get,
    triage_list,
)
from rootline.state import now

WORKFLOW = "support-ticket"
MAX_TRACES = 6
_SINCE = re.compile(r"^(?:last_)?(\d+)([hd])$")
_CHECKS = re.compile(r"failed_checks=(\[[^\]]*\])")


def window_start(since: str | None) -> str:
    """'last_24h', '7d', '48h' -> ISO timestamp. Unknown values mean 7 days."""
    match = _SINCE.match((since or "").strip().lower())
    hours = 24 * 7
    if match:
        amount = int(match.group(1))
        hours = amount * (24 if match.group(2) == "d" else 1)
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def as_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def rows(payload: dict, *keys: str) -> list:
    if not isinstance(payload, dict):
        return []
    for name in (*keys, "results", "traces"):
        value = payload.get(name)
        if isinstance(value, list):
            return value
    data = payload.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return rows(data, *keys)
    return []


def row_input(row: dict) -> dict:
    """ticket_id, git_sha and run_label come from the workflow span input preview."""
    return as_dict(row.get("input_preview"))


def row_passed(row: dict) -> bool | None:
    output = str(row.get("output_preview") or "").replace(" ", "")
    if '"passed":true' in output:
        return True
    if '"passed":false' in output:
        return False
    # A failing ticket raises inside the workflow span, so it has no verdict JSON.
    if str(row.get("status") or "").lower() == "error":
        return False
    return None


def verdict_from_spans(spans: list[dict]) -> dict:
    """Read the eval_check span the harness writes. Older traces fall back to the
    workflow span status and the failed_checks text in its error."""
    for span in spans:
        output = as_dict(span.get("output_value"))
        if span.get("name") == "eval_check" or ("failed_checks" in output and "passed" in output):
            return {"passed": bool(output.get("passed")), "failed_checks": list(output.get("failed_checks") or [])}
    for span in spans:
        if span.get("is_root") or span.get("name") == WORKFLOW:
            status = str(span.get("status") or "").lower()
            text = json.dumps(span)
            match = _CHECKS.search(text)
            checks = re.findall(r"'([a-z_]+)'", match.group(1)) if match else []
            return {"passed": status not in {"error", "failed"}, "failed_checks": checks}
    return {"passed": None, "failed_checks": []}


def _clip(value, limit: int = 600) -> str:
    text = value if isinstance(value, str) else json.dumps(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def evidence_from_context(row: dict, context: dict) -> dict:
    spans = context.get("spans") or []
    meta = row_input(row)
    root = next((span for span in spans if span.get("name") == WORKFLOW or span.get("is_root")), {})
    root_input = as_dict(root.get("input_value")) or meta
    tool_calls = []
    for span in spans:
        if str(span.get("type") or "").lower() in {"tool_call", "tool"} and span.get("name") != "eval_check":
            tool_calls.append(
                {
                    "tool": span.get("name"),
                    "status": span.get("status"),
                    "input": _clip(span.get("input_value") or "", 300),
                    "output": _clip(span.get("output_value") or "", 500),
                }
            )
    messages = root_input.get("messages") or []
    verdict = verdict_from_spans(spans)
    return {
        "trace_id": row.get("trace_id"),
        "created_at": row.get("created_at"),
        "ticket_id": root_input.get("ticket_id") or meta.get("ticket_id"),
        "git_sha": root_input.get("git_sha") or meta.get("git_sha"),
        "run_label": root_input.get("run_label") or meta.get("run_label"),
        "passed": verdict["passed"],
        "failed_checks": verdict["failed_checks"],
        "customer_message": _clip(messages[-1].get("content") if messages else "", 300),
        "reply": _clip(root.get("output_value") or row.get("output_preview") or "", 500),
        "tool_calls": tool_calls,
        "cost_usd": context.get("total_cost"),
        "detections": context.get("detections") or [],
    }


def on_branch(sha: str, branch: str) -> bool:
    try:
        git("merge-base", "--is-ancestor", sha, branch)
        return True
    except Exception:
        return False


def _signature(evidence: list[dict]) -> str:
    checks = sorted({name for item in evidence for name in item.get("failed_checks") or []})
    observed = ", ".join(checks) or "unknown"
    fallback = f"Support tickets fail the {observed} check."
    prompt = (
        "Write one plain sentence describing what the support agent did wrong, using only this trace "
        "evidence. Name the tool calls and values that show the failure. "
        f"Failed checks: {observed}.\n{json.dumps(evidence)[:7000]}"
    )
    try:
        text = complete("You write one factual sentence and nothing else.", prompt)
        return text.strip().splitlines()[0].strip() or fallback
    except Exception:
        return fallback


def scoreboard(found: list[dict]) -> dict:
    """Latest verdict per ticket for one commit, from neatlogs search rows."""
    latest: dict[str, dict] = {}
    for row in sorted(found, key=lambda item: item.get("created_at") or ""):
        meta = row_input(row)
        ticket = meta.get("ticket_id")
        passed = row_passed(row)
        if ticket and passed is not None:
            latest[ticket] = {"passed": passed, "trace_id": row.get("trace_id")}
        elif ticket and str(row.get("status") or "").lower() == "error":
            latest[ticket] = {"passed": False, "trace_id": row.get("trace_id")}
    passed = sum(1 for item in latest.values() if item["passed"])
    return {"passed": passed, "total": len(latest), "tickets": latest}


@neatlogs.span(kind="AGENT", name="detect")
def run(state: dict) -> dict:
    start = window_start(state.get("since"))
    branch = state["branch"]
    found = call_external(
        state,
        "DETECT",
        lambda: search_traces("failed_checks", limit=100, workflow_name=WORKFLOW, date_from=start),
    )
    candidates = [row for row in rows(found, "results") if row_passed(row) is not True]
    scoped = [row for row in candidates if on_branch(str(row_input(row).get("git_sha") or ""), branch)]
    if scoped:
        candidates = scoped
    candidates.sort(key=lambda row: row.get("created_at") or "", reverse=True)
    # Investigate the newest failing deployment. Older failures on ancestor commits
    # were already fixed or belong to a different investigation.
    current = next((row_input(row).get("git_sha") for row in candidates if row_input(row).get("git_sha")), None)
    if current:
        candidates = [row for row in candidates if row_input(row).get("git_sha") == current]

    failing: list[dict] = []
    seen: set[tuple] = set()
    for row in candidates:
        meta = row_input(row)
        key = (meta.get("ticket_id"), meta.get("git_sha"))
        if key in seen or not row.get("trace_id"):
            continue
        context = call_external(state, "DETECT", lambda tid=row["trace_id"]: get_trace_context(tid))
        item = evidence_from_context(row, context)
        seen.add(key)
        if item["passed"] is True:
            continue
        failing.append(item)
        if len(failing) >= MAX_TRACES:
            break

    bad_shas: list[str] = []
    for item in failing:
        sha = item.get("git_sha")
        if sha and sha not in bad_shas:
            bad_shas.append(sha)

    before = None
    if bad_shas:
        try:
            same_sha: list[dict] = []
            for offset in range(0, 500, 100):
                page = rows(
                    call_external(
                        state,
                        "DETECT",
                        lambda o=offset: search_traces(bad_shas[0], limit=100, offset=o, workflow_name=WORKFLOW, date_from=start),
                    ),
                    "results",
                )
                same_sha.extend(row for row in page if row_input(row).get("git_sha") == bad_shas[0])
                if len(page) < 100:
                    break
            before = scoreboard(same_sha)
        except Exception as exc:
            state["errors"].append({"step": "DETECT", "error": f"before: {exc}", "at": now()})

    last_good = None
    try:
        tickets = list(dict.fromkeys(item["ticket_id"] for item in failing if item.get("ticket_id")))[:3]
        good_rows = []
        for ticket in tickets:
            result = call_external(
                state,
                "DETECT",
                lambda t=ticket: search_traces(t, limit=50, workflow_name=WORKFLOW, date_from=window_start("30d")),
            )
            good_rows.extend(row for row in rows(result, "results") if row_input(row).get("ticket_id") == ticket)
        good_rows.sort(key=lambda row: row.get("created_at") or "", reverse=True)
        for row in good_rows:
            sha = str(row_input(row).get("git_sha") or "")
            if row_passed(row) and sha and sha not in bad_shas and sha != "unknown":
                last_good = sha
                break
    except Exception as exc:
        state["errors"].append({"step": "DETECT", "error": f"last_good: {exc}", "at": now()})

    detections = []
    try:
        listed = call_external(state, "DETECT", lambda: list_detections())
        for detection in rows(listed, "detections"):
            name = detection.get("display_name") or detection.get("slug")
            trend = call_external(state, "DETECT", lambda n=name: get_detection_trend(n, period="24h"))
            detections.append({"name": name, "description": detection.get("description"), "trend": trend})
    except Exception as exc:
        state["errors"].append({"step": "DETECT", "error": f"detections: {exc}", "at": now()})

    second_opinion = None
    try:
        cards = rows(call_external(state, "DETECT", lambda: triage_list()), "triage_cards", "fixes")
        ours = {item["trace_id"] for item in failing}
        matched = []
        for card in cards:
            linked = set(card.get("linked_traces") or card.get("trace_ids") or [])
            if linked and not (linked & ours):
                continue
            card_id = str(card.get("id") or "")
            if card_id:
                matched.append(call_external(state, "DETECT", lambda cid=card_id: triage_get(cid)))
        second_opinion = matched or None
    except Exception as exc:
        state["errors"].append({"step": "DETECT", "error": f"triage: {exc}", "at": now()})

    return {
        "window_start": start,
        "failing_traces": failing,
        "failure_signature": _signature(failing) if failing else "No failing support tickets found.",
        "bad_shas": bad_shas,
        "last_good_sha": last_good,
        "before": before,
        "detections": detections,
        "second_opinion": second_opinion,
    }
