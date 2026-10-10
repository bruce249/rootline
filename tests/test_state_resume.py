from __future__ import annotations

import rootline.state as state_mod
from rootline.runner import run_pending
from rootline.state import STEPS, load, new_state


def test_crash_after_locate_then_resume(tmp_path, monkeypatch):
    monkeypatch.setattr(state_mod, "RUNS", tmp_path)
    seen: list[str] = []

    def make(name: str):
        def _step(state):
            seen.append(name)
            if name == "EXPLAIN" and state["attempt"] == 1 and "resumed" not in state:
                raise RuntimeError("killed during explain")
            return {"step": name}

        return _step

    fns = {name: make(name) for name in STEPS}
    state = new_state("bench-r1")
    try:
        run_pending(state, fns)
    except RuntimeError as exc:
        assert "killed during explain" in str(exc)

    saved = load(state["run_id"])
    assert set(saved["outputs"]) == {"DETECT", "LOCATE"}
    assert saved["status"] == "FAILED"

    saved["resumed"] = True
    resumed_seen: list[str] = []

    def resume_step(name: str):
        def _step(resume_state):
            resumed_seen.append(name)
            return {"step": name, "resumed": True}

        return _step

    run_pending(saved, {name: resume_step(name) for name in STEPS})
    finished = load(state["run_id"])
    assert finished["status"] == "COMPLETE"
    assert set(finished["outputs"]) == set(STEPS)
    assert resumed_seen == ["EXPLAIN", "FIX", "VERIFY", "REPORT"]
    assert seen == ["DETECT", "LOCATE", "EXPLAIN"]
