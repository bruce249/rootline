from __future__ import annotations

import argparse
import random
import time

import neatlogs

from evals.harness import TICKETS
from evals.run_evals import run_suite
from patient.tracing import init_patient


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay random tickets as live traffic")
    parser.add_argument("--interval", type=float, default=8.0)
    parser.add_argument("--count", type=int, default=0, help="Stop after this many tickets. 0 runs until interrupted.")
    args = parser.parse_args()
    init_patient()
    ids = list(TICKETS)
    sent = 0
    try:
        while args.count == 0 or sent < args.count:
            ticket_id = random.choice(ids)
            print(f"live {ticket_id}")
            run_suite("live", [ticket_id])
            sent += 1
            time.sleep(args.interval)
    finally:
        neatlogs.flush()
        neatlogs.shutdown()


if __name__ == "__main__":
    main()
