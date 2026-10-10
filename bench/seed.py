from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

from rootline.clients.fixer import run_fixer

_ROOT = Path(__file__).resolve().parents[1]
_REGRESSIONS = Path(__file__).resolve().parent / "regressions.yaml"
_ANSWERS = Path(__file__).resolve().parent / "answers.yaml"


def _git(*args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=_ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(proc.stderr.strip() or proc.stdout.strip() or "git failed")
    return proc.stdout


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m bench.seed R1")
    regression_id = sys.argv[1]
    rows = yaml.safe_load(_REGRESSIONS.read_text(encoding="utf-8"))
    match = next(row for row in rows if row["id"] == regression_id)
    prompts = []
    if "stack" in match:
        for part in match["stack"]:
            prompts.append(next(row["prompt"] for row in rows if row["id"] == part))
    else:
        prompts.append(match["prompt"])
    _git("checkout", "main")
    _git("checkout", "-B", f"bench/{regression_id}")
    for prompt in prompts:
        text = f"{prompt} Only edit files under patient/."
        result = run_fixer(text, _ROOT)
        print(result["stdout"][-2000:])
        if result["returncode"] != 0:
            raise SystemExit(result["stderr"] or "fixer failed")
    _git("add", "patient")
    _git("commit", "-m", f"{regression_id}: {prompts[0][:60]}")
    print("Seed committed. Run `entire checkpoint explain HEAD` and confirm the transcript contains the prompt.")
    print("If no checkpoint was created, stop and seed this regression in an interactive agent session.")
    commit = _git("rev-parse", "HEAD").strip()
    files = [line[3:].strip() for line in _git("show", "--name-only", "--format=", "HEAD").splitlines() if line.strip()]
    answers = yaml.safe_load(_ANSWERS.read_text(encoding="utf-8")) or []
    answers.append({"id": regression_id, "commit": commit, "files": files, "prompt": prompts})
    _ANSWERS.write_text(yaml.safe_dump(answers, sort_keys=False), encoding="utf-8")
    print(f"appended {regression_id} to answers. Add assumption_quote from the transcript before scoring.")


if __name__ == "__main__":
    main()
