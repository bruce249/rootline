from __future__ import annotations

import subprocess


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "unknown"


def git_short_sha() -> str:
    full = git_sha()
    if full == "unknown":
        return full
    return full[:7]
