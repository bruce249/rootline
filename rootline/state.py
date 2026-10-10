from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

STEPS = ["DETECT", "LOCATE", "EXPLAIN", "FIX", "VERIFY", "REPORT"]
RUNS = Path(".rootline") / "runs"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_state(branch: str, since: str = "last_24h") -> dict:
    state = {
        "run_id": uuid.uuid4().hex[:12],
        "repo": os.environ.get("GITHUB_REPO", ""),
        "branch": branch,
        "since": since,
        "status": "RUNNING",
        "step_index": 0,
        "attempt": 1,
        "outputs": {},
        "errors": [],
        "started_at": now(),
        "updated_at": now(),
    }
    save(state)
    return state


def run_dir(run_id: str) -> Path:
    return RUNS / run_id


def state_path(run_id: str) -> Path:
    return run_dir(run_id) / "state.json"


def save(state: dict) -> None:
    state["updated_at"] = now()
    dest = state_path(state["run_id"])
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = dest.with_suffix(".json.tmp")
    temp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    temp.replace(dest)


def load(run_id: str) -> dict:
    return json.loads(state_path(run_id).read_text(encoding="utf-8"))


def next_step(state: dict) -> str | None:
    for index, name in enumerate(STEPS):
        if name not in state["outputs"]:
            state["step_index"] = index
            return name
    return None
