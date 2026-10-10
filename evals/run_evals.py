from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import neatlogs

_ROOT = Path(__file__).resolve().parents[1]
_OUT = _ROOT / "evals" / "out"


def use_patient_dir(path: str | None) -> Path:
    """Load the patient package from another checkout, keeping this harness and its checks.

    The harness is the monitor and stays fixed; the patient is the thing being
    replayed, so a regression branch or a fix worktree can be scored by the same checks.
    """
    if not path:
        return _ROOT
    patient_root = Path(path).resolve()
    if not (patient_root / "patient" / "__init__.py").exists():
        raise SystemExit(f"no patient package under {patient_root}")
    if "patient" in sys.modules:
        raise SystemExit("patient was imported before --patient-dir was applied")
    sys.path.insert(0, str(patient_root))
    return patient_root


def init_tracing() -> None:
    """The harness owns telemetry, so every replayed patient version is traced the
    same way and its spans are masked, including branches older than the mask."""
    import os

    from dotenv import load_dotenv

    import patient.tracing as tracing
    from evals.privacy import redact_pii

    if getattr(tracing, "_started", False):
        return
    load_dotenv(_ROOT / ".env")
    neatlogs.init(
        api_key=os.environ["NEATLOGS_API_KEY"],
        workflow_name="support-ticket",
        tags=["patient", "kettle-co"],
        mask=redact_pii,
    )
    from openai import OpenAI

    tracing._client = neatlogs.wrap(OpenAI())
    tracing._started = True


def _sha(root: Path, short: bool = False) -> str:
    args = ["git", "-C", str(root), "rev-parse"] + (["--short=7"] if short else []) + ["HEAD"]
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "unknown"


def run_suite(label: str, only: list[str] | None = None, patient_root: Path | None = None, session: str | None = None) -> dict:
    from evals.harness import TICKETS, run_one

    init_tracing()
    root = patient_root or _ROOT
    ids = only or list(TICKETS)
    unknown = [ticket_id for ticket_id in ids if ticket_id not in TICKETS]
    if unknown:
        raise SystemExit(f"unknown ticket ids: {', '.join(unknown)}")
    sha = _sha(root)
    short = _sha(root, short=True)
    results = []
    scope = neatlogs.identify(session_id=session) if session else contextlib.nullcontext()
    with scope:
        for ticket_id in ids:
            result = run_one(ticket_id, label, sha)
            results.append(result)
            status = "PASS" if result["passed"] else "FAIL"
            failed = ",".join(result.get("failed_checks") or [])
            print(f"{ticket_id:4}  {status:4}  {failed}", flush=True)
    passed = sum(1 for result in results if result["passed"])
    summary = {
        "label": label,
        "git_sha": sha,
        "git_short_sha": short,
        "session": session,
        "passed": passed,
        "total": len(results),
        "results": results,
    }
    _OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = _OUT / f"{label}-{short}-{stamp}.json"
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"{passed}/{len(results)} passed")
    print(f"WROTE {path}")
    neatlogs.flush()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Kettle & Co. support evals")
    parser.add_argument("--label", required=True)
    parser.add_argument("--only", default="", help="Comma-separated ticket ids")
    parser.add_argument("--patient-dir", default="", help="Checkout whose patient/ package is replayed")
    parser.add_argument("--session", default="", help="neatlogs session id that groups these traces")
    args = parser.parse_args()
    patient_root = use_patient_dir(args.patient_dir or None)
    only = [part.strip() for part in args.only.split(",") if part.strip()] or None
    try:
        run_suite(args.label, only, patient_root, args.session or None)
    finally:
        neatlogs.flush()
        neatlogs.shutdown()


if __name__ == "__main__":
    main()
