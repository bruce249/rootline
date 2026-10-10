from __future__ import annotations

import json
import os
import time
import webbrowser
from pathlib import Path

import neatlogs
import typer
from dotenv import load_dotenv

from rootline.clients.git import git
from rootline.runner import run_pending
from rootline.state import RUNS, load, new_state, save
from rootline.tracing import init_rootline

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _steps() -> dict:
    from rootline.steps.detect import run as detect
    from rootline.steps.explain import run as explain
    from rootline.steps.fix import run as fix
    from rootline.steps.guard import run as guard
    from rootline.steps.locate import run as locate
    from rootline.steps.report import run as report
    from rootline.steps.verify import run as verify

    return {
        "DETECT": detect,
        "LOCATE": locate,
        "EXPLAIN": explain,
        "FIX": fix,
        "VERIFY": verify,
        "GUARD": guard,
        "REPORT": report,
    }


def _setup() -> None:
    load_dotenv()
    try:
        from rootline.clients.entire import entire_bin

        folder = str(Path(entire_bin()).parent)
        if folder not in os.environ.get("PATH", ""):
            # git hooks and agent hooks call `entire` by name
            os.environ["PATH"] = folder + os.pathsep + os.environ.get("PATH", "")
    except FileNotFoundError:
        pass
    init_rootline()


def _branch(branch: str | None) -> str:
    if branch:
        return branch
    return git("rev-parse", "--abbrev-ref", "HEAD").strip()


def _traced(state: dict) -> dict:
    """One neatlogs trace per invocation, with every step as a child span."""

    @neatlogs.span(kind="WORKFLOW", name="rootline-investigation")
    def investigation(run_id: str, branch: str, attempt: int) -> dict:
        run_pending(state, _steps())
        return {"run_id": run_id, "status": state["status"], "attempt": state["attempt"]}

    try:
        return investigation(state["run_id"], state["branch"], state["attempt"])
    finally:
        neatlogs.flush()


@app.command()
def investigate(
    branch: str = typer.Option(None, help="Branch that contains the failing agent. Defaults to the current branch."),
    since: str = typer.Option("7d", help="How far back to read neatlogs traces: 24h, 7d, last_24h."),
) -> None:
    """Run DETECT through REPORT."""
    _setup()
    state = new_state(_branch(branch), since=since)
    typer.echo(f"run {state['run_id']} on {state['branch']}")
    try:
        _traced(state)
    finally:
        neatlogs.shutdown()
    typer.echo(state["status"])


@app.command()
def resume(run_id: str) -> None:
    """Continue a run at the first step that has no output."""
    _setup()
    state = load(run_id)
    state["resumed_at"] = state.get("resumed_at", []) + [time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())]
    save(state)
    try:
        _traced(state)
    finally:
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
        webbrowser.open(Path(html).resolve().as_uri())


@app.command()
def costs(
    write_business: bool = typer.Option(True, help="Also write business/unit_costs.json."),
) -> None:
    """Measure what investigations cost, from neatlogs traces of finished runs."""
    load_dotenv()
    from rootline.clients.neatlogs_mcp import search_traces
    from rootline.steps.detect import rows, window_start

    per_run = []
    for path in sorted(RUNS.glob("*/state.json")):
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("status") not in {"COMPLETE", "ESCALATED_TO_HUMAN"}:
            continue
        found = rows(search_traces(state["run_id"], limit=100, date_from=window_start("30d")), "results")
        rootline = [row for row in found if row.get("workflow_name") == "rootline-investigation" or row.get("root_span_name") == "rootline-investigation"]
        replays = [row for row in found if row.get("workflow_name") == "support-ticket"]
        cost = sum(float(row.get("cost_usd") or 0) for row in rootline + replays)
        tokens = sum(int(row.get("total_tokens") or 0) for row in rootline + replays)
        minutes = sum(float(row.get("duration_ms") or 0) for row in rootline) / 60000
        per_run.append(
            {
                "run_id": state["run_id"],
                "status": state["status"],
                "attempts": state.get("attempt"),
                "rootline_traces": len(rootline),
                "replay_traces": len(replays),
                "rootline_cost_usd": round(sum(float(row.get("cost_usd") or 0) for row in rootline), 6),
                "replay_cost_usd": round(sum(float(row.get("cost_usd") or 0) for row in replays), 6),
                "total_cost_usd": round(cost, 6),
                "total_tokens": tokens,
                "minutes": round(minutes, 2),
            }
        )
        typer.echo(json.dumps(per_run[-1]))
    tickets = rows(search_traces("support-ticket", limit=100, workflow_name="support-ticket", date_from=window_start("7d")), "results")
    ticket_costs = [float(row.get("cost_usd") or 0) for row in tickets if row.get("cost_usd")]
    out = {
        "source": "neatlogs search_traces over finished Rootline runs",
        "runs": per_run,
        "patient_avg_ticket_cost_usd": round(sum(ticket_costs) / len(ticket_costs), 6) if ticket_costs else None,
        "patient_tickets_sampled": len(ticket_costs),
    }
    Path("evidence").mkdir(exist_ok=True)
    Path("evidence/costs.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    typer.echo("WROTE evidence/costs.json")
    if write_business and per_run:
        business = Path("business/unit_costs.json")
        current = json.loads(business.read_text(encoding="utf-8")) if business.exists() else {}
        counted = [run for run in per_run if run["rootline_traces"]]
        if counted:
            current.update(
                {
                    "note": "Measured from neatlogs traces by `rootline costs`. EC2 cost is filled by hand.",
                    "investigations_measured": len(counted),
                    "avg_investigation_cost_usd": round(sum(r["total_cost_usd"] for r in counted) / len(counted), 4),
                    "avg_investigation_tokens": int(sum(r["total_tokens"] for r in counted) / len(counted)),
                    "avg_investigation_minutes": round(sum(r["minutes"] for r in counted) / len(counted), 2),
                    "patient_avg_ticket_cost_usd": out["patient_avg_ticket_cost_usd"],
                }
            )
            business.write_text(json.dumps(current, indent=2), encoding="utf-8")
            typer.echo(f"WROTE {business}")


@app.command()
def watch(
    interval: int = typer.Option(300, help="Seconds between checks."),
    branch: str = typer.Option(None, help="Branch to investigate when the failure rate is high."),
    window: int = typer.Option(20, help="How many recent tickets to score."),
) -> None:
    """Start an investigation when the recent ticket failure rate crosses the threshold."""
    _setup()
    from rootline.clients.neatlogs_mcp import search_traces
    from rootline.steps.detect import row_passed, rows, window_start

    threshold = float(os.environ.get("ROOTLINE_FAILURE_THRESHOLD", "0.15"))
    chosen = _branch(branch)
    while True:
        found = rows(search_traces("support-ticket", limit=window, workflow_name="support-ticket", date_from=window_start("1h")), "results")
        verdicts = [row_passed(row) for row in found]
        scored = [v for v in verdicts if v is not None]
        rate = (scored.count(False) / len(scored)) if scored else 0
        typer.echo(f"failure_rate={rate:.2f} n={len(scored)}")
        if scored and rate >= threshold:
            state = new_state(chosen, since="1h")
            _traced(state)
            typer.echo(f"investigated {state['run_id']} {state['status']}")
        time.sleep(interval)


if __name__ == "__main__":
    app()
