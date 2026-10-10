from __future__ import annotations

import json

import neatlogs

from rootline.clients.entire import checkpoint_explain, search
from rootline.clients.external import call_external
from rootline.clients.git import git
from rootline.clients.llm import complete, parse_json, read_prompt
from rootline.state import now

POLICY = "patient/policy/refund_policy.md"


def norm(text: str) -> str:
    return " ".join((text or "").split()).lower()


def quote_ok(quote: str, *sources: str) -> bool:
    wanted = norm(quote)
    return bool(wanted) and any(wanted in norm(source) for source in sources if source)


def policy_before(sha: str) -> str:
    """The policy as it stood before the suspect commit. A coding session can
    rewrite the policy file itself, so the current file is not a safe oracle."""
    try:
        return git("show", f"{sha}^:{POLICY}")
    except Exception:
        return ""


def _compact_traces(traces: list[dict]) -> list[dict]:
    keep = ("ticket_id", "failed_checks", "customer_message", "reply", "tool_calls")
    return [{key: trace.get(key) for key in keep} for trace in traces[:4]]


@neatlogs.span(kind="AGENT", name="explain")
def run(state: dict) -> dict:
    detect = state["outputs"]["DETECT"]
    locate = state["outputs"]["LOCATE"]
    signature = detect.get("failure_signature") or ""
    search_hits = ""
    try:
        search_hits = call_external(state, "EXPLAIN", lambda: search(signature, limit=5))
    except Exception as exc:
        state["errors"].append({"step": "EXPLAIN", "error": f"search: {exc}", "at": now()})

    chosen = None
    for suspect in (locate.get("candidates") or [])[:2]:
        sha = suspect["sha"]
        prov = suspect.get("provenance") or []
        prompts = sorted({item["prompt"] for item in prov if item.get("prompt")})
        checkpoint = next((item["checkpoint_id"] for item in prov if item.get("checkpoint_id")), None)
        transcript = ""
        evidence_level = "checkpoint"
        try:
            transcript = call_external(state, "EXPLAIN", lambda ref=checkpoint or sha: checkpoint_explain(ref, full=True))
        except Exception as exc:
            evidence_level = "diff_only"
            state["errors"].append({"step": "EXPLAIN", "error": f"checkpoint: {exc}", "at": now()})
        before = policy_before(sha)
        after = git("show", f"{sha}:{POLICY}") if suspect.get("edits_source_of_truth") else before
        user = json.dumps(
            {
                "failure_signature": signature,
                "failing_traces": _compact_traces(detect.get("failing_traces") or []),
                "commit": sha,
                "commit_subject": suspect.get("subject"),
                "diff": suspect.get("diff"),
                "session_prompts": prompts,
                "line_provenance": prov,
                "commit_edits_source_of_truth": bool(suspect.get("edits_source_of_truth")),
                "policy_before_commit": before,
                "policy_after_commit": after,
                "transcript": transcript[:16000],
                "entire_search_hits": search_hits[:3000],
            }
        )
        parsed = parse_json(complete(read_prompt("explain.md"), user))
        quote = str(parsed.get("assumption_quote") or "")
        if not quote_ok(quote, transcript, *prompts):
            parsed = parse_json(
                complete(
                    read_prompt("explain.md"),
                    user + "\nYour previous assumption_quote was not a verbatim substring of the transcript or session prompts. Copy the text exactly.",
                )
            )
            quote = str(parsed.get("assumption_quote") or "")
        verified = quote_ok(quote, transcript, *prompts)
        confidence = float(parsed.get("confidence") or 0)
        if not verified:
            confidence = min(confidence, 0.3)
        parsed.update(
            {
                "commit": sha,
                "assumption_quote": quote,
                "quote_verified": verified,
                "confidence": confidence,
                "evidence_level": evidence_level if transcript else "diff_only",
                "checkpoint_id": checkpoint,
                "session_prompts": prompts,
                "provenance": prov,
                "policy_tampered": bool(suspect.get("edits_source_of_truth")) and before != after,
                "policy_before": before,
                "transcript_excerpt": transcript[:2000],
            }
        )
        chosen = parsed
        if confidence >= 0.6:
            break
    if chosen is None:
        chosen = {"commit": "", "file": "", "assumption_quote": "", "why_wrong": "", "source_of_truth": "", "confidence": 0.0, "evidence_level": "none"}
    chosen["search_hits"] = search_hits[:3000]
    return chosen
