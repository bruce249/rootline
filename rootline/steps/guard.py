from __future__ import annotations

import neatlogs

from rootline.clients.neatlogs_mcp import (
    create_detection,
    list_detection_groups,
    list_detections,
    preview_detection,
)
from rootline.state import now
from rootline.steps.detect import rows

GROUP = "Negative"


def guard_spec(check: str) -> dict:
    """A regex detection on the harness's eval_check span for one failed check name."""
    return {
        "display_name": f"Rootline guard: {check} check failing",
        "kind": "regex",
        "config": {"output_pattern": f'"failed_checks":\\s*\\[[^\\]]*"{check}"', "case_sensitive": False},
        "run_on": {"frequency": "span_name", "span_names": ["eval_check"]},
    }


@neatlogs.span(kind="AGENT", name="guard")
def run(state: dict) -> dict:
    """Leave a neatlogs detection behind so this class of regression is flagged the
    moment it reaches traffic again, without waiting for an investigation."""
    detect = state["outputs"]["DETECT"]
    explain = state["outputs"].get("EXPLAIN") or {}
    checks = sorted({name for trace in detect.get("failing_traces") or [] for name in trace.get("failed_checks") or []})
    out = {"created": [], "existing": [], "skipped": [], "errors": []}
    if not checks:
        return out
    try:
        existing = {row.get("display_name") for row in rows(list_detections(), "detections")}
        groups = rows(list_detection_groups(), "groups")
        group_id = next((g["id"] for g in groups if g.get("name") == GROUP), groups[0]["id"] if groups else None)
    except Exception as exc:
        out["errors"].append(str(exc)[:300])
        return out
    for check in checks:
        spec = guard_spec(check)
        if spec["display_name"] in existing:
            out["existing"].append(spec["display_name"])
            continue
        try:
            preview = preview_detection(spec["kind"], spec["config"], spec["run_on"])
            flagged = int(preview.get("total_count") or 0)
            if flagged <= 0:
                out["skipped"].append({"name": spec["display_name"], "preview_count": flagged})
                continue
            created = create_detection(
                spec["display_name"],
                group_id,
                spec["kind"],
                spec["config"],
                description=(
                    f"Created by Rootline run {state['run_id']} after tracing a '{check}' regression to commit "
                    f"{str(explain.get('commit'))[:7]}: {explain.get('assumption_quote')}"
                )[:900],
                run_on=spec["run_on"],
            )
            out["created"].append({"name": spec["display_name"], "preview_count": flagged, "response": created})
        except Exception as exc:
            out["errors"].append(f"{check}: {str(exc)[:300]}")
            state["errors"].append({"step": "GUARD", "error": f"{check}: {exc}", "at": now()})
    return out
