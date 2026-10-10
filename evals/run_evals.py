from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import neatlogs

from evals.harness import TICKETS, run_one
from patient.tracing import init_patient
from patient.version import git_sha, git_short_sha

_OUT = Path(__file__).resolve().parent / "out"


def run_suite(label: str, only: list[str] | None = None) -> dict:
    init_patient()
    ids = only or list(TICKETS)
    unknown = [ticket_id for ticket_id in ids if ticket_id not in TICKETS]
    if unknown:
        raise SystemExit(f"unknown ticket ids: {', '.join(unknown)}")
    sha = git_sha()
    results = []
    for ticket_id in ids:
        result = run_one(ticket_id, label, sha)
        results.append(result)
        status = "PASS" if result["passed"] else "FAIL"
        failed = ",".join(result.get("failed_checks") or [])
        print(f"{ticket_id:4}  {status:4}  {failed}")
    passed = sum(1 for result in results if result["passed"])
    summary = {
        "label": label,
        "git_sha": sha,
        "git_short_sha": git_short_sha(),
        "passed": passed,
        "total": len(results),
        "results": results,
    }
    _OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = _OUT / f"{label}-{git_short_sha()}-{stamp}.json"
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"{passed}/{len(results)} passed")
    print(f"WROTE {path}")
    neatlogs.flush()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Kettle & Co. support evals")
    parser.add_argument("--label", required=True)
    parser.add_argument("--only", default="", help="Comma-separated ticket ids")
    args = parser.parse_args()
    only = [part.strip() for part in args.only.split(",") if part.strip()] or None
    try:
        run_suite(args.label, only)
    finally:
        neatlogs.flush()
        neatlogs.shutdown()


if __name__ == "__main__":
    main()
