from __future__ import annotations

import json
import re

import neatlogs

from rootline.clients.entire import graph_search, why
from rootline.clients.external import call_external
from rootline.clients.git import git, repo_root
from rootline.clients.llm import complete, parse_json, read_prompt
from rootline.clients.workspace import ensure_worktree
from rootline.state import now

SOURCE_OF_TRUTH = "patient/policy/"
MAX_WHY_LINES = 6
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def changed_lines(diff: str) -> list[dict]:
    """New-side line numbers and text of added lines in a -U0 diff."""
    out: list[dict] = []
    path = None
    line_no = 0
    for raw in diff.splitlines():
        if raw.startswith("+++ "):
            target = raw[4:].strip()
            path = None if target == "/dev/null" else target.removeprefix("b/")
            continue
        match = _HUNK.match(raw)
        if match:
            line_no = int(match.group(1))
            continue
        if path and raw.startswith("+") and not raw.startswith("+++"):
            out.append({"file": path, "line": line_no, "text": raw[1:]})
            line_no += 1
    return out


def commit_range(last_good: str | None, bad: str | None, branch: str) -> str | None:
    if not bad:
        return None
    if last_good:
        try:
            base = git("merge-base", last_good, bad).strip()
            if base and base != bad:
                return f"{base}..{bad}"
        except Exception:
            pass
    return None


def provenance(lines: list[dict], cwd, sha: str, state: dict) -> list[dict]:
    """Ask Entire which session, prompt and agent wrote each changed line."""
    found: list[dict] = []
    seen: set[str] = set()
    for item in lines:
        if len(found) >= MAX_WHY_LINES or not item["text"].strip():
            continue
        try:
            answer = why(item["file"], item["line"], cwd=cwd)
        except Exception as exc:
            state["errors"].append({"step": "LOCATE", "error": f"why {item['file']}:{item['line']}: {exc}", "at": now()})
            continue
        line = answer.get("line") or {}
        if line.get("commit_sha") and not str(line["commit_sha"]).startswith(sha[:7]):
            continue
        key = f"{line.get('checkpoint_id')}:{item['file']}"
        if key in seen:
            continue
        seen.add(key)
        found.append(
            {
                "file": item["file"],
                "line": item["line"],
                "content": line.get("content") or item["text"],
                "authorship": line.get("authorship"),
                "commit_sha": line.get("commit_sha"),
                "checkpoint_id": line.get("checkpoint_id"),
                "session_id": line.get("session_id"),
                "agent": line.get("agent"),
                "model": line.get("model"),
                "prompt": line.get("prompt"),
                "files_touched": (line.get("candidates") or [{}])[0].get("files_touched") or [],
            }
        )
    return found


def _candidates(state: dict, worktree) -> list[dict]:
    detect = state["outputs"]["DETECT"]
    bad = (detect.get("bad_shas") or [None])[0]
    span = commit_range(detect.get("last_good_sha"), bad, state["branch"])
    if span:
        log = git("log", "--format=%H%x09%s", span, "--", "patient/")
    else:
        log = git("log", "-n", "10", "--format=%H%x09%s", bad or state["branch"], "--", "patient/")
    out = []
    for line in log.splitlines():
        if "\t" not in line:
            continue
        sha, subject = line.split("\t", 1)
        diff = git("show", "--format=", "-U0", sha, "--", "patient/")
        files = [name for name in git("show", "--name-only", "--format=", sha, "--", "patient/").splitlines() if name]
        out.append(
            {
                "sha": sha,
                "subject": subject,
                "files": files,
                "diff": git("show", "--format=", sha, "--", "patient/")[:8000],
                "changed_lines": changed_lines(diff),
                "edits_source_of_truth": any(name.startswith(SOURCE_OF_TRUTH) for name in files),
            }
        )
    return out, span


@neatlogs.span(kind="AGENT", name="locate")
def run(state: dict) -> dict:
    signature = state["outputs"]["DETECT"].get("failure_signature") or ""
    worktree = ensure_worktree(state)
    candidates, span = call_external(state, "LOCATE", lambda: _candidates(state, worktree))
    for row in candidates:
        row["provenance"] = provenance(row["changed_lines"], worktree, row["sha"], state)

    graph_text = ""
    graph_error = None
    try:
        graph_text = call_external(state, "LOCATE", lambda: graph_search(signature, repo=repo_root()))
    except Exception as exc:
        graph_error = str(exc)[:500]

    ranking = []
    if len(candidates) == 1:
        ranking = [{"sha": candidates[0]["sha"], "score": 1.0, "reason": "only commit under patient/ between the last good and the first bad trace"}]
    elif candidates:
        try:
            packed = [
                {
                    "sha": row["sha"],
                    "subject": row["subject"],
                    "edits_source_of_truth": row["edits_source_of_truth"],
                    "session_prompts": sorted({p["prompt"] for p in row["provenance"] if p.get("prompt")}),
                    "diff": row["diff"][:2500],
                }
                for row in candidates[:8]
            ]
            raw = complete(read_prompt("rank.md"), f"Failure signature:\n{signature}\n\nCommits:\n{json.dumps(packed)}")
            ranking = parse_json(raw).get("ranking") or []
        except Exception as exc:
            state["errors"].append({"step": "LOCATE", "error": f"rank: {exc}", "at": now()})

    by_sha = {row["sha"]: row for row in candidates}
    ordered = []
    for item in ranking:
        sha = item.get("sha")
        if sha in by_sha and sha not in {row["sha"] for row in ordered}:
            chosen = dict(by_sha[sha])
            chosen["reason"] = item.get("reason") or ""
            chosen["score"] = float(item.get("score") or 0)
            ordered.append(chosen)
    for row in candidates:
        if row["sha"] not in {item["sha"] for item in ordered}:
            ordered.append({**row, "reason": "not ranked", "score": 0.0})
    return {
        "range": span,
        "worktree": str(worktree),
        "candidates": ordered[:3],
        "graph": graph_text[:6000],
        "graph_error": graph_error,
    }
