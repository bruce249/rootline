from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import neatlogs
from dotenv import load_dotenv


@neatlogs.span(kind="TOOL", tool_name="fixer")
def run_fixer(prompt: str, cwd: Path) -> dict:
    load_dotenv()
    agent = os.environ.get("FIXER_AGENT", "codex")
    if agent == "codex":
        if shutil.which("codex") is None:
            raise FileNotFoundError("codex is not installed")
        command = ["codex", "exec", "--full-auto", "-C", str(cwd), prompt]
    elif agent == "claude":
        if shutil.which("claude") is None:
            raise FileNotFoundError("claude is not installed")
        command = ["claude", "-p", prompt, "--permission-mode", "acceptEdits"]
    else:
        raise RuntimeError(f"unsupported FIXER_AGENT: {agent}")
    proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    return {
        "agent": agent,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-8000:],
        "stderr": proc.stderr[-4000:],
    }
