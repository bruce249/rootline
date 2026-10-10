"""Score investigations against ground truth. Numbers are written only after a real run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

_ANSWERS = Path(__file__).resolve().parent / "answers.yaml"
_EVIDENCE = Path(__file__).resolve().parents[1] / "evidence"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    answers = yaml.safe_load(_ANSWERS.read_text(encoding="utf-8")) or []
    if not answers:
        raise SystemExit("answers.yaml is empty. Seed regressions and add assumption quotes first.")
    payload = {"version": args.version, "rows": answers, "note": "scoring is filled by a real investigate run"}
    _EVIDENCE.mkdir(exist_ok=True)
    path = _EVIDENCE / f"bench_{args.version}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
