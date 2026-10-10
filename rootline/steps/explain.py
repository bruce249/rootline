from __future__ import annotations

import json
from pathlib import Path

import neatlogs

from rootline.clients.brain_mcp import available as brain_available
from rootline.clients.entire import checkpoint_explain, search
from rootline.clients.external import call_external
from rootline.clients.llm import complete, parse_json, read_prompt

_POLICY = Path("patient/policy/refund_policy.md")


def _norm(text: str) -> str:
    return " ".join((text or "").split())


def _quote_ok(quote: str, transcript: str) -> bool:
    if not quote or not transcript:
        return False
    return _norm(quote) in _norm(transcript)


@neatlogs.span(kind="AGENT", name="explain")
def run(state: dict) -> dict:
    detect = state["outputs"]["DETECT"]
    locate = state["outputs"]["LOCATE"]
    suspects = list(locate.get("candidates") or [])
    policy = _POLICY.read_text(encoding="utf-8") if _POLICY.exists() else ""
    signature = detect.get("failure_signature") or ""
    search_hits = ""
    try:
        search_hits = call_external(state, "EXPLAIN", lambda: search(signature, limit=5))
    except Exception as exc:
        state["errors"].append({"step": "EXPLAIN", "error": f"search: {exc}", "at": state.get("updated_at")})
    brain_note = None
    if brain_available():
        brain_note = "brain command is installed; no query schema was confirmed, so no lesson was fetched"
    chosen = None
    for suspect in suspects[:2]:
        transcript = ""
        evidence_level = "checkpoint"
        try:
            transcript = call_external(state, "EXPLAIN", lambda sha=suspect["sha"]: checkpoint_explain(sha))
        except Exception as exc:
            evidence_level = "diff_only"
            state["errors"].append({"step": "EXPLAIN", "error": f"checkpoint: {exc}", "at": state.get("updated_at")})
        user = json.dumps(
            {
                "signature": signature,
                "failing_traces": detect.get("failing_traces"),
                "commit": suspect.get("sha"),
                "diff": suspect.get("diff"),
                "transcript": transcript[:12000],
                "search_hits": search_hits[:4000],
                "policy": policy,
            }
        )
        parsed = parse_json(complete(read_prompt("explain.md"), user))
        quote = str(parsed.get("assumption_quote") or "")
        if transcript and not _quote_ok(quote, transcript):
            parsed = parse_json(
                complete(
                    read_prompt("explain.md"),
                    user + "\nThe previous assumption_quote was not a verbatim substring of the transcript. Quote the transcript exactly.",
                )
            )
            quote = str(parsed.get("assumption_quote") or "")
        confidence = float(parsed.get("confidence") or 0)
        if not _quote_ok(quote, transcript):
            confidence = min(confidence, 0.3)
            if not transcript:
                evidence_level = "diff_only"
        parsed.update(
            {
                "commit": parsed.get("commit") or suspect.get("sha"),
                "assumption_quote": quote,
                "confidence": confidence,
                "evidence_level": evidence_level,
                "transcript_excerpt": transcript[:2000],
            }
        )
        chosen = parsed
        if confidence >= 0.6:
            break
    if chosen is None:
        chosen = {
            "commit": "",
            "file": "",
            "assumption_quote": "",
            "why_wrong": "",
            "source_of_truth": policy.splitlines()[0] if policy else "",
            "confidence": 0.0,
            "evidence_level": "diff_only",
        }
    chosen["brain"] = brain_note
    chosen["search_hits"] = search_hits[:4000]
    return chosen
