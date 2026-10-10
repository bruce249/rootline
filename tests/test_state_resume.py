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
            return {"step": name, "failing_traces": [{"ticket_id": "T06"}]}

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
            return {"step": name, "resumed": True, "failing_traces": [{"ticket_id": "T06"}]}

        return _step

    run_pending(saved, {name: resume_step(name) for name in STEPS})
    finished = load(state["run_id"])
    assert finished["status"] == "COMPLETE"
    assert set(finished["outputs"]) == set(STEPS)
    assert resumed_seen == ["EXPLAIN", "FIX", "VERIFY", "GUARD", "REPORT"]
    assert seen == ["DETECT", "LOCATE", "EXPLAIN"]


def test_healthy_detect_stops_the_run(tmp_path, monkeypatch):
    monkeypatch.setattr(state_mod, "RUNS", tmp_path)
    seen: list[str] = []

    def step(name):
        def _step(state):
            seen.append(name)
            return {"failing_traces": []}

        return _step

    state = run_pending(new_state("main"), {name: step(name) for name in STEPS})
    assert state["status"] == "HEALTHY"
    assert seen == ["DETECT"]


def test_verify_failures_retry_then_escalate_with_report(tmp_path, monkeypatch):
    from rootline.runner import RetryFix

    monkeypatch.setattr(state_mod, "RUNS", tmp_path)
    calls: list[str] = []

    def step(name):
        def _step(state):
            calls.append(name)
            if name == "VERIFY":
                raise RetryFix(f"attempt {state['attempt']} still failing")
            return {"failing_traces": [{"ticket_id": "T06"}], "commit": f"c{state['attempt']}"}

        return _step

    state = run_pending(new_state("main"), {name: step(name) for name in STEPS})
    assert state["status"] == "ESCALATED_TO_HUMAN"
    assert calls.count("FIX") == 3
    assert [a["attempt"] for a in state["attempts"]] == [1, 2, 3]
    assert "REPORT" in state["outputs"]
