from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import neatlogs
from dotenv import load_dotenv

from rootline.clients.entire import entire_bin


def _argv(name: str, args: list[str]) -> list[str]:
    resolved = shutil.which(name)
    if resolved is None:
        raise FileNotFoundError(f"{name} is not installed")
    if os.name == "nt":
        # npm installs a .cmd shim; cmd.exe runs it. The prompt goes over stdin,
        # because cmd.exe cuts arguments at the first newline.
        return ["cmd.exe", "/d", "/c", name, *args]
    return [resolved, *args]


def _env() -> dict:
    """Put the Entire CLI on PATH so the agent's Entire hooks record a checkpoint."""
    env = dict(os.environ)
    try:
        folder = str(Path(entire_bin()).parent)
    except FileNotFoundError:
        return env
    env["PATH"] = folder + os.pathsep + env.get("PATH", "")
    return env


@neatlogs.span(kind="TOOL", tool_name="fixer")
def run_fixer(prompt: str, cwd: Path, timeout: int = 1200) -> dict:
    load_dotenv()
    agent = os.environ.get("FIXER_AGENT", "claude")
    if agent == "codex":
        command = _argv("codex", ["exec", "--full-auto", "--sandbox", "workspace-write", "-C", str(cwd), "-"])
    elif agent == "claude":
        command = _argv("claude", ["-p", "--permission-mode", "acceptEdits", "--output-format", "text"])
    else:
        raise RuntimeError(f"unsupported FIXER_AGENT: {agent}")
    proc = subprocess.run(
        command,
        cwd=cwd,
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_env(),
        timeout=timeout,
    )
    return {
        "agent": agent,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-8000:],
        "stderr": proc.stderr[-4000:],
    }
