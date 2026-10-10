from __future__ import annotations

import time
from collections.abc import Callable

from rootline.state import now, save


def call_external(state: dict, step: str, fn: Callable):
    """Try a transient external call 4 times, waiting 2s, 4s, then 8s between tries."""
    delay = 2.0
    for attempt in range(4):
        try:
            return fn()
        except FileNotFoundError:
            raise
        except Exception as exc:
            state["errors"].append({"step": step, "error": str(exc), "at": now()})
            save(state)
            if attempt == 3:
                raise
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"{step} failed")
