from __future__ import annotations

import shutil
import subprocess

import neatlogs


def _require() -> None:
    if shutil.which("entire") is None:
        raise FileNotFoundError("entire CLI is not installed")


def _run(args: list[str]) -> str:
    _require()
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "entire command failed").strip()
        raise RuntimeError(detail)
    return proc.stdout


@neatlogs.span(kind="TOOL", tool_name="entire_checkpoint_explain")
def checkpoint_explain(sha_or_id: str) -> str:
    return _run(["entire", "checkpoint", "explain", sha_or_id])


@neatlogs.span(kind="TOOL", tool_name="entire_checkpoint_list")
def checkpoint_list() -> str:
    return _run(["entire", "checkpoint", "list"])


@neatlogs.span(kind="TOOL", tool_name="entire_search")
def search(query: str, limit: int = 5) -> str:
    return _run(["entire", "search", query, "--compact", "--limit", str(limit)])


@neatlogs.span(kind="TOOL", tool_name="entire_graph_search")
def graph_search(query: str) -> str:
    if shutil.which("entire-graph") is not None:
        return _run(["entire-graph", "search", query])
    return _run(["entire", "graph", "search", query])


@neatlogs.span(kind="TOOL", tool_name="entire_graph_stats")
def graph_stats() -> str:
    return _run(["entire", "graph", "stats", "--repo", "."])


@neatlogs.span(kind="TOOL", tool_name="entire_status")
def status() -> str:
    return _run(["entire", "status"])


@neatlogs.span(kind="TOOL", tool_name="entire_trail_create")
def trail_create(branch: str, title: str) -> str:
    help_text = _run(["entire", "trail", "create", "--help"])
    command = ["entire", "trail", "create"]
    if "--branch" in help_text:
        command.extend(["--branch", branch])
    if "--title" in help_text:
        command.extend(["--title", title])
    elif "-t" in help_text:
        command.extend(["-t", title])
    if "--yes" in help_text:
        command.append("--yes")
    elif "\n  -y," in help_text or "\n  -y " in help_text:
        command.append("-y")
    return _run(command)
