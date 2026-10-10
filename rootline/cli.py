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

    from rootline.clients.llm import USAGE

    seen = len(USAGE)
    try:
        return investigation(state["run_id"], state["branch"], state["attempt"])
    finally:
        calls = USAGE[seen:]
        usage = state.setdefault("llm_usage", {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "models": []})
        usage["calls"] += len(calls)
        usage["prompt_tokens"] += sum(call["prompt_tokens"] for call in calls)
        usage["completion_tokens"] += sum(call["completion_tokens"] for call in calls)
        usage["models"] = sorted(set(usage["models"]) | {call["model"] for call in calls})
        save(state)
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


def _window_rows(query: str, workflow: str, start: str, end: str) -> list[dict]:
    from rootline.clients.neatlogs_mcp import search_traces
    from rootline.steps.detect import rows

    out: list[dict] = []
    for offset in range(0, 1000, 100):
        page = rows(search_traces(query, limit=100, offset=offset, workflow_name=workflow, date_from=start, date_to=end), "results")
        out.extend(page)
        if len(page) < 100:
            break
    return out


def _shift(stamp: str, minutes: int) -> str:
    from datetime import datetime, timedelta

    moment = datetime.fromisoformat(stamp) + timedelta(minutes=minutes)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


@app.command()
def costs(
    write_business: bool = typer.Option(True, help="Also write business/unit_costs.json."),
) -> None:
    """Measure what investigations cost, from neatlogs traces of finished runs."""
    load_dotenv()
    from datetime import datetime

    from rootline.steps.detect import as_dict, row_input, rows, window_start
    from rootline.clients.neatlogs_mcp import search_traces

    per_run = []
    for path in sorted(RUNS.glob("*/state.json")):
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("status") not in {"COMPLETE", "ESCALATED_TO_HUMAN"}:
            continue
        run_id = state["run_id"]
        start, end = _shift(state["started_at"], -1), _shift(state["updated_at"], 2)
        rootline = [
            row
            for row in _window_rows("rootline-investigation", "rootline-investigation", start, end)
            if as_dict(row.get("input_preview")).get("run_id") == run_id
        ]
        replays = [
            row
            for row in _window_rows("support-ticket", "support-ticket", start, end)
            if str(row_input(row).get("run_label") or "").startswith(f"replay-after-{run_id}")
        ]
        expected = 24 * int(state.get("attempt") or 1)
        minutes = (datetime.fromisoformat(state["updated_at"]) - datetime.fromisoformat(state["started_at"])).total_seconds() / 60
        resumed = bool(state.get("resumed_at"))
        per_run.append(
            {
                "run_id": run_id,
                "status": state["status"],
                "attempts": state.get("attempt"),
                "resumed": resumed,
                "rootline_traces": len(rootline),
                "replay_traces_found": len(replays),
                "replay_traces_expected": expected,
                "rootline_cost_usd": round(sum(float(row.get("cost_usd") or 0) for row in rootline), 6),
                "rootline_tokens": sum(int(row.get("total_tokens") or 0) for row in rootline),
                "replay_cost_usd": round(sum(float(row.get("cost_usd") or 0) for row in replays), 6),
                "replay_tokens": sum(int(row.get("total_tokens") or 0) for row in replays),
                "wall_minutes": round(minutes, 2),
                "rootline_llm_usage_local": state.get("llm_usage"),
            }
        )
        typer.echo(json.dumps(per_run[-1]))
    tickets = rows(search_traces("support-ticket", limit=100, workflow_name="support-ticket", date_from=window_start("7d")), "results")
    ticket_costs = [float(row.get("cost_usd") or 0) for row in tickets if row.get("cost_usd")]
    patient_avg = sum(ticket_costs) / len(ticket_costs) if ticket_costs else None
    out = {
        "source": "neatlogs search_traces, matched by run id and replay label inside each run's time window",
        "note": "Fixer agent tokens are recorded by Entire per checkpoint, not in neatlogs.",
        "runs": per_run,
        "patient_avg_ticket_cost_usd": round(patient_avg, 6) if patient_avg else None,
        "patient_tickets_sampled": len(ticket_costs),
    }
    Path("evidence").mkdir(exist_ok=True)
    Path("evidence/costs.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    typer.echo("WROTE evidence/costs.json")
    # Only runs whose traces are fully ingested count toward unit costs.
    complete = [
        run for run in per_run
        if run["rootline_traces"] and not run["resumed"] and run["replay_traces_found"] >= run["replay_traces_expected"]
    ]
    if not complete:
        typer.echo("no fully ingested, unresumed run yet; business/unit_costs.json left unchanged")
        return
    if write_business:
        business = Path("business/unit_costs.json")
        current = json.loads(business.read_text(encoding="utf-8")) if business.exists() else {}
        cost = [run["rootline_cost_usd"] + run["replay_cost_usd"] for run in complete]
        tokens = [run["rootline_tokens"] + run["replay_tokens"] for run in complete]
        current.update(
            {
                "note": "Measured from neatlogs traces by `rootline costs`. Excludes the fixer agent (tracked by Entire). EC2 is filled by hand.",
                "investigations_measured": len(complete),
                "measured_run_ids": [run["run_id"] for run in complete],
                "avg_investigation_cost_usd": round(sum(cost) / len(cost), 4),
                "avg_investigation_tokens": int(sum(tokens) / len(tokens)),
                "avg_investigation_minutes": round(sum(run["wall_minutes"] for run in complete) / len(complete), 2),
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
