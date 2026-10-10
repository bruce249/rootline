from __future__ import annotations

import json
import os
from pathlib import Path

import neatlogs
from dotenv import load_dotenv
from jinja2 import Template

from rootline.clients.git import git
from rootline.state import run_dir

_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "report.html.j2"


def _checkpoint_url(sha: str) -> str:
    load_dotenv()
    repo = os.environ.get("GITHUB_REPO", "")
    if not repo or not sha:
        return ""
    return f"https://entire.io/gh/{repo}/commit/{sha}"


@neatlogs.span(kind="AGENT", name="report")
def run(state: dict) -> dict:
    detect = state["outputs"].get("DETECT") or {}
    explain = state["outputs"].get("EXPLAIN") or {}
    fix = state["outputs"].get("FIX") or {}
    verify = state["outputs"].get("VERIFY") or {}
    diff = ""
    if fix.get("commit"):
        try:
            diff = git("show", "--format=", fix["commit"])
        except Exception as exc:
            diff = f"diff unavailable: {exc}"
    payload = {
        "run_id": state["run_id"],
        "status": "COMPLETE" if state.get("status") == "RUNNING" else state.get("status"),
        "failure_signature": detect.get("failure_signature"),
        "detections": detect.get("detections") or [],
        "before_traces": detect.get("failing_traces") or [],
        "verify": verify,
        "assumption_quote": explain.get("assumption_quote"),
        "why_wrong": explain.get("why_wrong"),
        "source_of_truth": explain.get("source_of_truth"),
        "confidence": explain.get("confidence"),
        "bad_checkpoint_url": _checkpoint_url(str(explain.get("commit") or "")),
        "fix_checkpoint_url": _checkpoint_url(str(fix.get("commit") or "")),
        "trail": fix.get("trail"),
        "diff": diff,
        "second_opinion": detect.get("second_opinion"),
        "attempts": state.get("attempt"),
        "errors": state.get("errors") or [],
        "fix_mode": fix.get("fix_mode"),
        "brain": explain.get("brain"),
    }
    dest = run_dir(state["run_id"])
    dest.mkdir(parents=True, exist_ok=True)
    json_path = dest / "report.json"
    html_path = dest / "report.html"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    html = Template(_TEMPLATE.read_text(encoding="utf-8")).render(**payload)
    html_path.write_text(html, encoding="utf-8")
    evidence = Path("evidence")
    evidence.mkdir(exist_ok=True)
    public_html = evidence / f"report-{state['run_id']}.html"
    public_json = evidence / f"report-{state['run_id']}.json"
    public_html.write_text(html, encoding="utf-8")
    public_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"json": str(json_path), "html": str(html_path), "public_html": str(public_html)}
