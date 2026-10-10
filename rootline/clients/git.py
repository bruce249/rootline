from __future__ import annotations

import subprocess
from pathlib import Path

import neatlogs


def repo_root() -> Path:
    return Path(
        subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
    )


@neatlogs.span(kind="TOOL", tool_name="git")
def git(*args: str, cwd: str | Path | None = None) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd or repo_root()),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or "git failed"
        raise RuntimeError(detail)
    return proc.stdout
