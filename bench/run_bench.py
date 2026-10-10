"""Score Rootline investigations against ground truth. Numbers come only from real runs.

    python -m bench.run_bench --version v2                 # latest finished run per bench branch
    python -m bench.run_bench --version v1 --run R1=f43fa9505b8c
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
_ANSWERS = Path(__file__).resolve().parent / "answers.yaml"
_RUNS = _ROOT / ".rootline" / "runs"
_EVIDENCE = _ROOT / "evidence"


def _norm(text: str) -> str:
    return " ".join((text or "").split()).lower()


def _runs() -> list[dict]:
    out = []
    for path in _RUNS.glob("*/state.json"):
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return sorted(out, key=lambda state: state.get("started_at") or "")


def _seconds(state: dict) -> float | None:
    try:
        start = datetime.fromisoformat(state["started_at"])
        end = datetime.fromisoformat(state["updated_at"])
    except (KeyError, ValueError):
        return None
    return round((end - start).total_seconds(), 1)


def score(answer: dict, state: dict, costs: dict) -> dict:
    outputs = state.get("outputs") or {}
    explain = outputs.get("EXPLAIN") or {}
    verify = outputs.get("VERIFY") or {}
    detect = outputs.get("DETECT") or {}
    found = str(explain.get("commit") or "")
    truth = str(answer.get("commit") or "")
    quote = _norm(explain.get("assumption_quote") or "")
    wanted = _norm(answer.get("assumption_quote") or "")
    prompts = [_norm(p) for p in (answer.get("prompt") if isinstance(answer.get("prompt"), list) else [answer.get("prompt") or ""])]
    cost = next((row for row in costs.get("runs") or [] if row.get("run_id") == state["run_id"]), {})
    before = detect.get("before") or {}
    return {
        "id": answer["id"],
        "run_id": state["run_id"],
        "status": state.get("status"),
        "commit_correct": bool(found and truth and (found.startswith(truth[:7]) or truth.startswith(found[:7]))),
        "found_commit": found[:12],
        "quote_match": bool(quote and ((wanted and (wanted in quote or quote in wanted)) or any(quote in p for p in prompts if p))),
        "quote_verified_in_transcript": bool(explain.get("quote_verified")),
        "policy_tamper_detected": bool(explain.get("policy_tampered")),
        "fix_verified": bool(verify.get("passed")),
        "before": f"{before.get('passed')}/{before.get('total')}" if before else None,
        "after": f"{verify.get('after_passed')}/{verify.get('after_total')}" if verify else None,
        "attempts": state.get("attempt"),
        "duration_s": _seconds(state),
        "cost_usd": cost.get("total_cost_usd"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--run", action="append", default=[], help="ID=RUN_ID to score a specific run")
    args = parser.parse_args()
    answers = yaml.safe_load(_ANSWERS.read_text(encoding="utf-8")) or []
    if not answers:
        raise SystemExit("answers.yaml is empty. Seed regressions and add assumption quotes first.")
    pinned = dict(item.split("=", 1) for item in args.run)
    runs = _runs()
    by_id = {state["run_id"]: state for state in runs}
    costs_path = _EVIDENCE / "costs.json"
    costs = json.loads(costs_path.read_text(encoding="utf-8")) if costs_path.exists() else {}
    rows = []
    for answer in answers:
        state = by_id.get(pinned.get(answer["id"], ""))
        if state is None:
            branch = f"bench/{answer['id']}"
            finished = [s for s in runs if s.get("branch") == branch and s.get("status") in {"COMPLETE", "ESCALATED_TO_HUMAN"}]
            state = finished[-1] if finished else None
        if state is None:
            rows.append({"id": answer["id"], "status": "NOT_RUN"})
            continue
        rows.append(score(answer, state, costs))
    scored = [row for row in rows if row.get("status") != "NOT_RUN"]
    total = {
        "runs": len(scored),
        "commit_correct": sum(row["commit_correct"] for row in scored),
        "quote_match": sum(row["quote_match"] for row in scored),
        "fix_verified": sum(row["fix_verified"] for row in scored),
    }
    payload = {"version": args.version, "totals": total, "rows": rows}
    _EVIDENCE.mkdir(exist_ok=True)
    (_EVIDENCE / f"bench_{args.version}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    cols = ["id", "run_id", "status", "commit_correct", "quote_match", "policy_tamper_detected", "fix_verified", "before", "after", "attempts", "duration_s", "cost_usd"]
    lines = [f"# Bench {args.version}", "", "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(col, "")) for col in cols) + " |")
    lines += ["", f"Commit correct {total['commit_correct']}/{total['runs']} · quote match {total['quote_match']}/{total['runs']} · fix verified {total['fix_verified']}/{total['runs']}"]
    (_EVIDENCE / f"bench_{args.version}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
