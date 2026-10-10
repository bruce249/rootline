from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import neatlogs

from rootline.clients.git import repo_root
from rootline.clients.neatlogs_mcp import triage_accept, triage_update, triage_update_status
from rootline.clients.workspace import ensure_worktree
from rootline.runner import RetryFix
from rootline.state import now


def run_evals(label: str, patient_dir: Path, session: str, only: list[str] | None = None) -> dict:
    """Replay tickets with this checkout's harness against the patient in patient_dir."""
    root = repo_root()
    command = [sys.executable, "-m", "evals.run_evals", "--label", label, "--patient-dir", str(patient_dir), "--session", session]
    if only:
        command.extend(["--only", ",".join(only)])
    proc = subprocess.run(command, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout)[-2000:])
    wrote = ""
    for line in proc.stdout.splitlines():
        if line.startswith("WROTE "):
            wrote = line.split(" ", 1)[1].strip()
    if not wrote:
        raise RuntimeError("eval runner did not write a results file")
    return json.loads(Path(wrote).read_text(encoding="utf-8"))


def failing(summary: dict) -> list[dict]:
    return [
        {"ticket_id": row["ticket_id"], "failed_checks": row.get("failed_checks") or []}
        for row in summary.get("results") or []
        if not row.get("passed")
    ]


@neatlogs.span(kind="AGENT", name="verify")
def run(state: dict) -> dict:
    detect = state["outputs"]["DETECT"]
    fix = state["outputs"]["FIX"]
    cwd = ensure_worktree(state)
    run_id = state["run_id"]
    attempt = state.get("attempt", 1)
    summary = run_evals(f"replay-after-{run_id}-a{attempt}", cwd, session=f"rootline-{run_id}")
    still = failing(summary)
    target = sorted({item["ticket_id"] for item in detect.get("failing_traces") or [] if item.get("ticket_id")})
    before = detect.get("before") or {}
    result = {
        "passed": not still,
        "after_passed": summary.get("passed"),
        "after_total": summary.get("total"),
        "after_sha": summary.get("git_sha"),
        "before_passed": before.get("passed"),
        "before_total": before.get("total"),
        "target_tickets": target,
        "target_fixed": [ticket for ticket in target if ticket not in {item["ticket_id"] for item in still}],
        "still_failing": still,
        "attempt": attempt,
        "fix_commit": fix.get("commit"),
    }
    if still:
        detail = "; ".join(f"{item['ticket_id']} {item['failed_checks']}" for item in still)
        raise RetryFix(f"verify attempt {attempt}: {summary.get('passed')}/{summary.get('total')} passed; still failing: {detail}")

    notes = []
    explain = state["outputs"].get("EXPLAIN") or {}
    for card in detect.get("second_opinion") or []:
        card_id = str((card or {}).get("id") or (card or {}).get("triage_id") or "")
        if not card_id:
            continue
        try:
            if str(card.get("status") or "").lower() == "draft":
                triage_accept(card_id)
            triage_update(
                card_id,
                root_cause=f"Commit {str(explain.get('commit'))[:7]}: \"{explain.get('assumption_quote')}\". {explain.get('why_wrong')}",
                evidence_reasoning=f"Rootline run {run_id}: {before.get('passed')}/{before.get('total')} before, {summary.get('passed')}/{summary.get('total')} after.",
            )
            triage_update_status(card_id, "resolved", f"Verified by Rootline run {run_id}, fix {str(fix.get('commit'))[:7]}")
            notes.append({"triage_id": card_id, "ok": True})
        except Exception as exc:
            notes.append({"triage_id": card_id, "ok": False, "error": str(exc)[:300]})
            state["errors"].append({"step": "VERIFY", "error": f"triage {card_id}: {exc}", "at": now()})
    result["triage_updates"] = notes
    return result
