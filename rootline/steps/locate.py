from __future__ import annotations

import json

import neatlogs

from rootline.clients.entire import graph_search
from rootline.clients.external import call_external
from rootline.clients.git import git
from rootline.clients.llm import complete, parse_json, read_prompt


def _candidates(state: dict) -> list[dict]:
    detect = state["outputs"]["DETECT"]
    last_good = detect.get("last_good_sha")
    bad = (detect.get("bad_shas") or [None])[0]
    if last_good and bad:
        rev = f"{last_good}..{bad}"
    else:
        rev = "-n"
    if rev == "-n":
        log = git("log", "-n", "20", "--format=%H%x09%s", "--", "patient/")
    else:
        log = git("log", "--format=%H%x09%s", rev, "--", "patient/")
    rows = []
    for line in log.splitlines():
        if "\t" not in line:
            continue
        sha, subject = line.split("\t", 1)
        stat = git("show", "--stat", "--format=", sha, "--", "patient/")
        diff = git("show", "--format=", sha, "--", "patient/")
        rows.append({"sha": sha, "subject": subject, "stat": stat, "diff": diff[:8000]})
    return rows


def _overlap(diff: str, hints: str) -> float:
    score = 0.0
    lowered = f"{diff}\n{hints}".lower()
    for token in ("refund", "policy", "config", "inventory", "escalat", "history", "prompt", "paise"):
        if token in diff.lower() and token in lowered:
            score += 0.1
    return score


@neatlogs.span(kind="AGENT", name="locate")
def run(state: dict) -> dict:
    signature = state["outputs"]["DETECT"].get("failure_signature") or ""
    graph_text = ""
    graph_error = None
    try:
        graph_text = call_external(state, "LOCATE", lambda: graph_search(signature))
    except Exception as exc:
        graph_error = str(exc)
    candidates = call_external(state, "LOCATE", lambda: _candidates(state))
    for row in candidates:
        row["overlap"] = _overlap(row["diff"], f"{graph_text}\n{signature}")
    ranking = []
    try:
        packed = [{"sha": row["sha"], "subject": row["subject"], "diff": row["diff"][:2500]} for row in candidates[:8]]
        raw = complete(
            read_prompt("rank.md"),
            f"Failure signature:\n{signature}\n\nCommits:\n{json.dumps(packed)}",
        )
        ranking = parse_json(raw).get("ranking") or []
    except Exception as exc:
        state["errors"].append({"step": "LOCATE", "error": f"rank: {exc}", "at": state.get("updated_at")})
    by_sha = {row["sha"]: row for row in candidates}
    ordered = []
    for item in ranking:
        sha = item.get("sha")
        if sha in by_sha and sha not in {row["sha"] for row in ordered}:
            chosen = dict(by_sha[sha])
            chosen["reason"] = item.get("reason") or ""
            chosen["score"] = float(item.get("score") or chosen["overlap"])
            ordered.append(chosen)
    if not ordered:
        ordered = sorted(candidates, key=lambda row: row["overlap"], reverse=True)
        for row in ordered:
            row["reason"] = "ranked by overlap with the failure signature"
            row["score"] = row["overlap"]
    top = []
    for row in ordered[:3]:
        top.append(
            {
                "sha": row["sha"],
                "subject": row["subject"],
                "reason": row.get("reason", ""),
                "score": row.get("score", 0),
                "stat": row.get("stat", ""),
                "diff": row.get("diff", ""),
            }
        )
    return {"candidates": top, "graph": graph_text[:8000], "graph_error": graph_error}
