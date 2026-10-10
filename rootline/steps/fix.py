from __future__ import annotations

from pathlib import Path

import neatlogs
from jinja2 import Template

from rootline.clients.entire import trail_create
from rootline.clients.fixer import run_fixer
from rootline.clients.git import git, repo_root
from rootline.clients.llm import complete, read_prompt

_POLICY = "patient/policy/refund_policy.md"


def _changed() -> list[str]:
    files = []
    for line in git("status", "--porcelain").splitlines():
        if len(line) < 4:
            continue
        files.append(line[3:].strip().strip('"'))
    return files


def _restore_forbidden() -> list[str]:
    restored = []
    for path in _changed():
        if path == _POLICY or not path.startswith("patient/"):
            git("checkout", "--", path)
            restored.append(path)
    return restored


def _llm_patch(state: dict, brief: str, root: Path) -> None:
    diff = complete(
        "Return only a unified diff that applies with git apply. No prose.",
        brief,
    )
    start = diff.find("diff --git")
    if start < 0:
        raise RuntimeError("model did not return a unified diff")
    patch = root / ".rootline" / "patch.diff"
    patch.parent.mkdir(parents=True, exist_ok=True)
    patch.write_text(diff[start:], encoding="utf-8")
    git("apply", str(patch), cwd=root)


@neatlogs.span(kind="AGENT", name="fix")
def run(state: dict) -> dict:
    root = repo_root()
    explain = state["outputs"]["EXPLAIN"]
    detect = state["outputs"]["DETECT"]
    run_id = state["run_id"]
    branch = f"rootline/fix-{run_id}"
    previous = [item["error"] for item in state.get("errors") or [] if item.get("step") in {"FIX", "VERIFY"}]
    failing = []
    for trace in detect.get("failing_traces") or []:
        if trace.get("ticket_id"):
            failing.append(trace["ticket_id"])
    brief = Template(read_prompt("fixer_brief.md")).render(
        assumption_quote=explain.get("assumption_quote") or "",
        why_wrong=explain.get("why_wrong") or "",
        source_of_truth=explain.get("source_of_truth") or "",
        failing_tickets=", ".join(dict.fromkeys(failing)) or "unknown",
        previous_failures="\n".join(previous) or "none",
    )
    git("checkout", state["branch"], cwd=root)
    existing = git("branch", "--list", branch, cwd=root).strip()
    if existing:
        git("checkout", branch, cwd=root)
    else:
        git("checkout", "-b", branch, cwd=root)
    mode = "agent"
    fixer_result = None
    try:
        fixer_result = run_fixer(brief, root)
        if fixer_result["returncode"] != 0:
            raise RuntimeError(fixer_result["stderr"] or "fixer failed")
    except Exception as exc:
        mode = "llm_patch"
        state["errors"].append({"step": "FIX", "error": f"fixer: {exc}", "at": state.get("updated_at")})
        _llm_patch(state, brief, root)
    restored = _restore_forbidden()
    if not any(path.startswith("patient/") for path in _changed()):
        raise RuntimeError("no changes under patient/ to commit")
    git("add", "patient", cwd=root)
    short = str(explain.get("commit") or "unknown")[:7]
    git("commit", "-m", f"fix({run_id}): revert wrong assumption from {short}", cwd=root)
    commit = git("rev-parse", "HEAD", cwd=root).strip()
    pushed = False
    push_error = None
    try:
        git("push", "-u", "origin", branch, cwd=root)
        pushed = True
    except Exception as exc:
        push_error = str(exc)
    trail = None
    trail_error = None
    try:
        trail = trail_create(branch, f"Rootline fix {run_id}")
    except Exception as exc:
        trail_error = str(exc)
    return {
        "branch": branch,
        "commit": commit,
        "fix_mode": mode,
        "fixer": fixer_result,
        "restored": restored,
        "pushed": pushed,
        "push_error": push_error,
        "trail": trail,
        "trail_error": trail_error,
        "brief": brief,
    }
