from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import neatlogs


def entire_bin() -> str:
    """Locate the Entire CLI. The Windows installer puts it in ~/.local/bin, which
    is not always on PATH for subprocesses."""
    configured = os.environ.get("ENTIRE_BIN", "").strip()
    if configured:
        return configured
    found = shutil.which("entire")
    if found:
        return found
    for name in ("entire.exe", "entire"):
        candidate = Path.home() / ".local" / "bin" / name
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError("entire CLI is not installed (set ENTIRE_BIN)")


def _run(args: list[str], cwd: str | Path | None = None, timeout: int = 300) -> str:
    proc = subprocess.run(
        [entire_bin(), *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
        timeout=timeout,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "entire command failed").strip()
        raise RuntimeError(detail)
    return proc.stdout


def _json(text: str):
    text = (text or "").strip()
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise ValueError("entire returned no JSON")
    return json.loads(text[start:])


@neatlogs.span(kind="TOOL", tool_name="entire_checkpoint_explain")
def checkpoint_explain(sha_or_id: str, full: bool = True, cwd: str | Path | None = None) -> str:
    args = ["checkpoint", "explain", sha_or_id]
    if full:
        args.append("--full")
    return _run(args, cwd=cwd)


@neatlogs.span(kind="TOOL", tool_name="entire_checkpoint_list")
def checkpoint_list(cwd: str | Path | None = None) -> str:
    return _run(["checkpoint", "list"], cwd=cwd)


@neatlogs.span(kind="TOOL", tool_name="entire_search")
def search(query: str, limit: int = 5, branch: str | None = None) -> str:
    args = ["search", query, "--compact", "--limit", str(limit)]
    if branch:
        args.extend(["--branch", branch])
    return _run(args)


@neatlogs.span(kind="TOOL", tool_name="entire_why")
def why(path: str, line: int, cwd: str | Path | None = None) -> dict:
    """Commit, checkpoint, session, agent and prompt behind one line of code."""
    return _json(_run(["why", f"{path}:{line}", "--json"], cwd=cwd, timeout=120))


@neatlogs.span(kind="TOOL", tool_name="entire_graph_search")
def graph_search(query: str, repo: str | Path = ".") -> str:
    return _run(
        ["graph", "search", "--repo", str(repo), "--query", query, "--profile", "full", "--format", "json", "--top-k", "8"],
        timeout=600,
    )


@neatlogs.span(kind="TOOL", tool_name="entire_graph_stats")
def graph_stats() -> str:
    return _run(["graph", "stats", "--repo", "."])


@neatlogs.span(kind="TOOL", tool_name="entire_status")
def status() -> str:
    return _run(["status"])


@neatlogs.span(kind="TOOL", tool_name="entire_trail_create")
def trail_create(branch: str, title: str, body: str, base: str | None = None, cwd: str | Path | None = None) -> str:
    args = ["trail", "create", "--branch", branch, "--title", title, "--body", body, "--type", "bug", "--priority", "high"]
    if base:
        args.extend(["--base", base])
    return _run(args, cwd=cwd)


@neatlogs.span(kind="TOOL", tool_name="entire_trail_finding_add")
def trail_finding_add(
    branch: str,
    body: str,
    confidence: float,
    severity: str = "high",
    file: str | None = None,
    line: int | None = None,
    patch_file: str | Path | None = None,
    client_id: str | None = None,
    cwd: str | Path | None = None,
) -> str:
    args = [
        "trail", "finding", "add",
        "--branch", branch,
        "--body", body,
        "--confidence", f"{max(0.0, min(1.0, confidence)):.2f}",
        "--severity", severity,
        "--json",
    ]
    if patch_file:
        args.extend(["--patch-file", str(patch_file)])
    if file:
        args.extend(["--file", file])
    if line:
        args.extend(["--line", str(line)])
    if client_id:
        args.extend(["--client-id", client_id])
    return _run(args, cwd=cwd)
