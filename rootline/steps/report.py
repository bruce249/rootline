from __future__ import annotations

import json
import os
from pathlib import Path

import neatlogs
from dotenv import load_dotenv
from jinja2 import Environment

from rootline.clients.git import git
from rootline.state import run_dir

_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "report.html.j2"


def _commit_url(sha: str) -> str:
    load_dotenv()
    repo = os.environ.get("GITHUB_REPO", "")
    if not repo or not sha:
        return ""
    return f"https://entire.io/gh/{repo}/commit/{sha}"


def _github_url(sha: str) -> str:
    repo = os.environ.get("GITHUB_REPO", "")
    return f"https://github.com/{repo}/commit/{sha}" if repo and sha else ""


@neatlogs.span(kind="AGENT", name="report")
def run(state: dict) -> dict:
    outputs = state.get("outputs") or {}
    detect = outputs.get("DETECT") or {}
    locate = outputs.get("LOCATE") or {}
    explain = outputs.get("EXPLAIN") or {}
    fix = outputs.get("FIX") or {}
    verify = outputs.get("VERIFY") or {}
    guard = outputs.get("GUARD") or {}
    diff = ""
    if fix.get("commit"):
        try:
            diff = git("show", "--format=", fix["commit"])
        except Exception as exc:
            diff = f"diff unavailable: {exc}"
    bad = str(explain.get("commit") or "")
    status = state.get("status")
    payload = {
        "run_id": state["run_id"],
        "branch": state.get("branch"),
        "status": "COMPLETE" if status == "RUNNING" else status,
        "started_at": state.get("started_at"),
        "updated_at": state.get("updated_at"),
        "attempt": state.get("attempt"),
        "attempts": state.get("attempts") or [],
        "failure_signature": detect.get("failure_signature"),
        "failing_traces": detect.get("failing_traces") or [],
        "before": detect.get("before") or {},
        "last_good_sha": detect.get("last_good_sha"),
        "detections": detect.get("detections") or [],
        "second_opinion": detect.get("second_opinion"),
        "range": locate.get("range"),
        "candidates": [
            {key: row.get(key) for key in ("sha", "subject", "score", "reason", "files", "edits_source_of_truth")}
            for row in locate.get("candidates") or []
        ],
        "graph_used": bool(locate.get("graph")),
        "graph_error": locate.get("graph_error"),
        "bad_commit": bad,
        "bad_commit_url": _commit_url(bad),
        "bad_github_url": _github_url(bad),
        "provenance": explain.get("provenance") or [],
        "assumption_quote": explain.get("assumption_quote"),
        "quote_verified": explain.get("quote_verified"),
        "why_wrong": explain.get("why_wrong"),
        "source_of_truth": explain.get("source_of_truth"),
        "restore": explain.get("restore"),
        "policy_tampered": explain.get("policy_tampered"),
        "confidence": explain.get("confidence"),
        "evidence_level": explain.get("evidence_level"),
        "fix": {key: fix.get(key) for key in ("branch", "commit", "files", "fix_mode", "restored_source_of_truth", "pushed", "push_error", "trail", "trail_error", "finding", "finding_error")},
        "fix_commit_url": _commit_url(str(fix.get("commit") or "")),
        "diff": diff,
        "verify": verify,
        "guard": guard,
        "errors": state.get("errors") or [],
    }
    dest = run_dir(state["run_id"])
    dest.mkdir(parents=True, exist_ok=True)
    json_path = dest / "report.json"
    html_path = dest / "report.html"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    env = Environment(autoescape=True)
    html = env.from_string(_TEMPLATE.read_text(encoding="utf-8")).render(**payload)
    html_path.write_text(html, encoding="utf-8")
    evidence = Path("evidence")
    evidence.mkdir(exist_ok=True)
    public_html = evidence / f"report-{state['run_id']}.html"
    public_json = evidence / f"report-{state['run_id']}.json"
    public_html.write_text(html, encoding="utf-8")
    public_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"json": str(json_path), "html": str(html_path), "public_html": str(public_html)}
