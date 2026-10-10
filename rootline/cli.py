from __future__ import annotations

import os
import time
import webbrowser

import neatlogs
import typer
from dotenv import load_dotenv

from rootline.clients.git import git
from rootline.runner import run_pending
from rootline.state import load, new_state
from rootline.tracing import init_rootline

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _steps() -> dict:
    from rootline.steps.detect import run as detect
    from rootline.steps.explain import run as explain
    from rootline.steps.fix import run as fix
    from rootline.steps.locate import run as locate
    from rootline.steps.report import run as report
    from rootline.steps.verify import run as verify

    return {
        "DETECT": detect,
        "LOCATE": locate,
        "EXPLAIN": explain,
        "FIX": fix,
        "VERIFY": verify,
        "REPORT": report,
    }


def _branch(branch: str | None) -> str:
    if branch:
        return branch
    return git("rev-parse", "--abbrev-ref", "HEAD").strip()


@app.command()
def investigate(
    branch: str = typer.Option(None, help="Branch that contains the failing agent. Defaults to the current branch."),
    since: str = typer.Option("last_24h", help="neatlogs date_range filter."),
) -> None:
    """Run DETECT through REPORT."""
    load_dotenv()
    init_rootline()
    state = new_state(_branch(branch), since=since)
    try:
        run_pending(state, _steps())
    finally:
        neatlogs.flush()
        neatlogs.shutdown()
    typer.echo(state["run_id"])
    typer.echo(state["status"])


@app.command()
def resume(run_id: str) -> None:
    """Continue a run at the first step that has no output."""
    load_dotenv()
    init_rootline()
    state = load(run_id)
    try:
        run_pending(state, _steps())
    finally:
        neatlogs.flush()
        neatlogs.shutdown()
    typer.echo(state["status"])


@app.command()
def report(
    run_id: str,
    open_browser: bool = typer.Option(False, "--open", help="Open the HTML report."),
) -> None:
    """Print the report path for a finished run."""
    state = load(run_id)
    info = (state.get("outputs") or {}).get("REPORT") or {}
    html = info.get("public_html") or info.get("html") or ""
    typer.echo(html or "no report yet")
    if open_browser and html:
        webbrowser.open(Path_to_uri(html))


def Path_to_uri(path: str) -> str:
    from pathlib import Path

    return Path(path).resolve().as_uri()


@app.command()
def watch(
    interval: int = typer.Option(300, help="Seconds between checks."),
    branch: str = typer.Option(None, help="Branch to investigate when the error rate is high."),
) -> None:
    """Start an investigation when the recent error rate crosses the threshold."""
    load_dotenv()
    from rootline.clients.neatlogs_mcp import search_traces

    threshold = float(os.environ.get("ROOTLINE_FAILURE_THRESHOLD", "0.15"))
    chosen = _branch(branch)
    while True:
        found = search_traces("support-ticket", limit=20, filters={"date_range": "last_24h"})
        traces = found.get("traces") or found.get("data") or []
        if isinstance(traces, dict):
            traces = traces.get("traces") or []
        total = len(traces)
        errors = sum(1 for trace in traces if str(trace.get("status", "")).lower() == "error")
        rate = (errors / total) if total else 0
        typer.echo(f"error_rate={rate:.2f} n={total}")
        if total and rate >= threshold:
            init_rootline()
            state = new_state(chosen, since="last_24h")
            run_pending(state, _steps())
            neatlogs.flush()
            typer.echo(f"investigated {state['run_id']} {state['status']}")
        time.sleep(interval)


if __name__ == "__main__":
    app()
