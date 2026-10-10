from __future__ import annotations

import json
from pathlib import Path

import neatlogs
from jinja2 import Template

from rootline.clients.entire import trail_create, trail_finding_add
from rootline.clients.fixer import run_fixer
from rootline.clients.git import git
from rootline.clients.llm import complete, read_prompt
from rootline.clients.workspace import ensure_worktree
from rootline.state import now

POLICY = "patient/policy/refund_policy.md"
_UNTOUCHABLE_PREFIXES = ("evals/", "tests/", "rootline/")


def changed(cwd: Path) -> list[tuple[str, str]]:
    files = []
    for line in git("status", "--porcelain", cwd=cwd).splitlines():
        if len(line) < 4:
            continue
        files.append((line[:2], line[3:].strip().strip('"')))
    return files


def enforce_scope(cwd: Path, policy_ref: str | None) -> list[str]:
    """Undo edits outside patient/, and pin the policy to the pre-regression text."""
    restored = []
    for status, path in changed(cwd):
        if "?" in status:
            continue
        if path == POLICY:
            continue
        if path.startswith("patient/") and not path.startswith(_UNTOUCHABLE_PREFIXES):
            continue
        git("checkout", "--", path, cwd=cwd)
        restored.append(path)
    if policy_ref:
        git("checkout", policy_ref, "--", POLICY, cwd=cwd)
    else:
        git("checkout", "HEAD", "--", POLICY, cwd=cwd)
    return restored


def _llm_patch(brief: str, cwd: Path) -> None:
    diff = complete("Return only a unified diff against the files shown, that applies with git apply. No prose.", brief)
    start = diff.find("diff --git")
    if start < 0:
        start = diff.find("--- a/")
    if start < 0:
        raise RuntimeError("model did not return a unified diff")
    patch = cwd / ".rootline-patch.diff"
    patch.write_text(diff[start:], encoding="utf-8")
    try:
        git("apply", "--recount", str(patch), cwd=cwd)
    finally:
        patch.unlink(missing_ok=True)


def _ticket_summary(traces: list[dict]) -> str:
    lines = []
    for trace in traces:
        tools = ", ".join(f"{call['tool']}({call['input']})" for call in trace.get("tool_calls") or [])
        lines.append(f"- {trace.get('ticket_id')}: failed {trace.get('failed_checks')}; tools: {tools}")
    return "\n".join(lines) or "unknown"


@neatlogs.span(kind="AGENT", name="fix")
def run(state: dict) -> dict:
    explain = state["outputs"]["EXPLAIN"]
    detect = state["outputs"]["DETECT"]
    run_id = state["run_id"]
    branch = f"rootline/fix-{run_id}"
    cwd = ensure_worktree(state)
    bad = str(explain.get("commit") or "")
    policy_ref = f"{bad}^" if explain.get("policy_tampered") and bad else None

    if git("branch", "--list", branch, cwd=cwd).strip():
        git("checkout", "--force", branch, cwd=cwd)
    else:
        git("checkout", "--force", "-B", branch, state["branch"], cwd=cwd)

    previous = [item["error"] for item in state.get("errors") or [] if item.get("step") == "VERIFY"]
    brief = Template(read_prompt("fixer_brief.md")).render(
        assumption_quote=explain.get("assumption_quote") or "",
        why_wrong=explain.get("why_wrong") or "",
        source_of_truth=explain.get("source_of_truth") or "",
        restore=explain.get("restore") or "",
        policy_before=explain.get("policy_before") or "",
        policy_tampered=bool(policy_ref),
        bad_commit=bad[:12],
        failing_tickets=_ticket_summary(detect.get("failing_traces") or []),
        previous_failures="\n".join(previous) or "none",
    )

    if policy_ref:
        git("checkout", policy_ref, "--", POLICY, cwd=cwd)

    mode = "agent"
    fixer_result = None
    try:
        fixer_result = run_fixer(brief, cwd)
        if fixer_result["returncode"] != 0:
            raise RuntimeError((fixer_result["stderr"] or fixer_result["stdout"] or "fixer failed")[-1500:])
    except Exception as exc:
        mode = "llm_patch"
        state["errors"].append({"step": "FIX", "error": f"fixer: {exc}", "at": now()})
        _llm_patch(brief + "\n\nCurrent files:\n" + _files_for_patch(cwd), cwd)

    restored = enforce_scope(cwd, policy_ref)
    if not any(path.startswith("patient/") for _status, path in changed(cwd)):
        raise RuntimeError("fixer left no changes under patient/")
    git("add", "patient", cwd=cwd)
    message = (
        f"fix({run_id}): undo wrong assumption from {bad[:7]}\n\n"
        f"Assumption: {explain.get('assumption_quote') or 'unknown'}\n"
        f"Source of truth: {explain.get('source_of_truth') or 'patient/policy/refund_policy.md'}\n"
        f"Rootline-Run: {run_id}"
    )
    git("commit", "-m", message, cwd=cwd)
    commit = git("rev-parse", "HEAD", cwd=cwd).strip()
    files = [name for name in git("show", "--name-only", "--format=", commit, cwd=cwd).splitlines() if name]

    pushed, push_error = False, None
    try:
        git("push", "--force-with-lease", "-u", "origin", branch, cwd=cwd)
        pushed = True
    except Exception as exc:
        push_error = str(exc)[:500]

    trail, trail_error, finding, finding_error = None, None, None, None
    if pushed:
        body = (
            f"Rootline run {run_id}.\n\n"
            f"Failure: {detect.get('failure_signature')}\n\n"
            f"Wrong assumption in {bad[:7]}: \"{explain.get('assumption_quote')}\"\n\n"
            f"Why wrong: {explain.get('why_wrong')}\n\n"
            f"Source of truth: {explain.get('source_of_truth')}"
        )
        try:
            trail = trail_create(branch, f"Rootline: {detect.get('failure_signature', '')[:80]}", body, base=state["branch"], cwd=cwd)
        except Exception as exc:
            trail_error = str(exc)[:500]
        try:
            target = next((item for item in explain.get("provenance") or [] if item.get("file") == explain.get("file")), None)
            target = target or next(iter(explain.get("provenance") or []), {})
            finding = trail_finding_add(
                branch,
                body=(
                    f"Introduced by {target.get('agent') or 'a coding agent'} session {target.get('session_id') or ''} "
                    f"(checkpoint {target.get('checkpoint_id') or 'n/a'}) in {bad[:7]}.\n"
                    f"Prompt: {target.get('prompt') or 'n/a'}\n\n"
                    f"Assumption: \"{explain.get('assumption_quote')}\"\n{explain.get('why_wrong')}"
                ),
                confidence=float(explain.get("confidence") or 0),
                file=target.get("file") or explain.get("file") or None,
                line=target.get("line"),
                client_id=f"rootline-{run_id}-{state.get('attempt', 1)}",
                cwd=cwd,
            )
        except Exception as exc:
            finding_error = str(exc)[:500]

    return {
        "branch": branch,
        "commit": commit,
        "files": files,
        "fix_mode": mode,
        "restored_source_of_truth": bool(policy_ref),
        "fixer": fixer_result,
        "restored": restored,
        "pushed": pushed,
        "push_error": push_error,
        "trail": trail,
        "trail_error": trail_error,
        "finding": finding,
        "finding_error": finding_error,
        "brief": brief,
    }


def _files_for_patch(cwd: Path) -> str:
    parts = []
    for name in ("patient/config.py", "patient/prompts/system.md", "patient/tools/__init__.py"):
        path = cwd / name
        if path.exists():
            parts.append(f"=== {name}\n{path.read_text(encoding='utf-8')}")
    return json.dumps(parts)[:20000]
