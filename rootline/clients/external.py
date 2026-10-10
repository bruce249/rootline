from __future__ import annotations

import time
from collections.abc import Callable

from rootline.state import now, save


def call_external(state: dict, step: str, fn: Callable):
    """Retry a transient external call 3 times, waiting 1s, 2s, then 4s."""
    delay = 1.0
    for attempt in range(3):
        try:
            return fn()
        except FileNotFoundError:
            raise
        except Exception as exc:
            state["errors"].append({"step": step, "error": str(exc), "at": now()})
            save(state)
            if attempt == 2:
                raise
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"{step} failed")
