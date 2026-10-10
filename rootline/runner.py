from __future__ import annotations

from rootline.state import next_step, now, save

MAX_ATTEMPTS = 3


class RetryFix(Exception):
    """VERIFY failed and another FIX attempt is allowed."""


def run_pending(state: dict, step_fns: dict) -> dict:
    while True:
        name = next_step(state)
        if name is None:
            state["status"] = "COMPLETE"
            save(state)
            return state
        try:
            state["outputs"][name] = step_fns[name](state)
            state["status"] = "RUNNING"
            save(state)
            if name == "DETECT" and not state["outputs"][name].get("failing_traces"):
                state["status"] = "HEALTHY"
                save(state)
                return state
        except RetryFix as exc:
            state["errors"].append({"step": name, "error": str(exc), "at": now()})
            state.setdefault("attempts", []).append(
                {"attempt": state["attempt"], "fix": state["outputs"].get("FIX", {}).get("commit"), "verify": str(exc)}
            )
            if state["attempt"] >= MAX_ATTEMPTS:
                state["status"] = "ESCALATED_TO_HUMAN"
                save(state)
                if "REPORT" in step_fns:
                    state["outputs"]["REPORT"] = step_fns["REPORT"](state)
                    save(state)
                return state
            state["attempt"] += 1
            state["outputs"].pop("FIX", None)
            state["outputs"].pop("VERIFY", None)
            state["status"] = "RUNNING"
            save(state)
        except Exception as exc:
            state["errors"].append({"step": name, "error": str(exc), "at": now()})
            state["status"] = "FAILED"
            save(state)
            raise
