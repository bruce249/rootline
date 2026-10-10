from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import neatlogs

from rootline.clients.git import repo_root
from rootline.clients.neatlogs_mcp import triage_accept, triage_update_status
from rootline.runner import RetryFix


def _run_evals(root: Path, label: str, only: list[str] | None) -> dict:
    command = [sys.executable, "-m", "evals.run_evals", "--label", label]
    if only:
        command.extend(["--only", ",".join(only)])
    proc = subprocess.run(command, cwd=root, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout)[-2000:])
    wrote = ""
    for line in proc.stdout.splitlines():
        if line.startswith("WROTE "):
            wrote = line.split(" ", 1)[1].strip()
    if not wrote:
        raise RuntimeError("eval runner did not write a results file")
    return json.loads(Path(wrote).read_text(encoding="utf-8"))


def _failing_ids(summary: dict) -> list[str]:
    return [row["ticket_id"] for row in summary.get("results") or [] if not row.get("passed")]


@neatlogs.span(kind="AGENT", name="verify")
def run(state: dict) -> dict:
    root = repo_root()
    detect = state["outputs"]["DETECT"]
    wanted = []
    for trace in detect.get("failing_traces") or []:
        ticket_id = trace.get("ticket_id")
        if ticket_id and ticket_id not in wanted:
            wanted.append(ticket_id)
    focused = _run_evals(root, "replay-after", wanted or None)
    full = _run_evals(root, "replay-after-full", None)
    focused_failed = _failing_ids(focused)
    full_failed = _failing_ids(full)
    passed = not focused_failed and not full_failed
    result = {
        "passed": passed,
        "focused_passed": focused.get("passed"),
        "focused_total": focused.get("total"),
        "full_passed": full.get("passed"),
        "full_total": full.get("total"),
        "still_failing": full_failed,
        "attempt": state.get("attempt"),
    }
    if not passed:
        raise RetryFix(
            f"verify failed on attempt {state.get('attempt')}: {', '.join(full_failed) or ', '.join(focused_failed)}"
        )
    opinions = detect.get("second_opinion") or []
    notes = []
    for opinion in opinions:
        fix = (opinion or {}).get("fix") or {}
        fix_id = str(fix.get("id") or "")
        if not fix_id:
            continue
        try:
            if str(fix.get("status") or "").lower() == "draft":
                triage_accept(fix_id)
            triage_update_status(fix_id, "resolved", f"verified by Rootline run {state['run_id']}")
            notes.append(fix_id)
        except Exception as exc:
            notes.append(f"{fix_id}: {exc}")
    result["triage_updates"] = notes
    return result
