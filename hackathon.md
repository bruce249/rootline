# Rootline

## Project

Rootline finds the exact reasoning mistake in a coding session that made a production support agent start failing, fixes it, and proves the fix. The patient is a customer-support agent for the fictional tea brand Kettle & Co.

## Team

Heisenberg. Handles to publish are still pending.

## Stack

- Python 3.12, OpenAI (`gpt-5-mini` for the patient, `gpt-5` for Rootline)
- neatlogs SDK (tracing, PII mask, sessions) and MCP (trace search and context, detections, triage)
- Entire: checkpoints, `entire why`, search, graph, Trails with findings
- Claude Code (`claude -p`) as the headless fixer; Codex is supported through `FIXER_AGENT=codex`
- cfo.ai business plan, not started
- AWS EC2 in us-east-1, not started. Team allowance is $25. One instance, Hackathon_VPC, t3.small, when the watch demo is ready.

## How each sponsor tool is used

### neatlogs

- **Tracing.** Every support ticket is a `support-ticket` WORKFLOW trace with the agent, LLM and tool spans, plus an `eval_check` span holding the verdict and failed checks. Every Rootline run is one `rootline-investigation` trace with DETECT through REPORT as child spans. Replays are grouped by neatlogs session (`rootline-<run_id>`).
- **PII mask.** `lookup_order` returns customer phone numbers and emails on purpose. The harness masks them before spans leave the process, so they are not stored in neatlogs, while the eval still catches a leak in the reply.
- **MCP, DETECT.** `search_traces` (workflow and date filters) finds failing tickets. `get_trace_context` reads the tool calls that show the failure. `list_detections` and `get_detection_trend` give the detection picture, and `triage_list` checks for a matching neatlogs fix card.
- **MCP, GUARD.** After a verified fix, Rootline runs `preview_detection` and then `create_detection`, leaving a regex detection on `eval_check` spans for the failed check. The first R1 run created **"Rootline guard: refund check failing"** (preview flagged 4 spans). Later runs found it and did not duplicate it.
- **MCP, VERIFY.** If a triage card matches, Rootline writes the root cause with `triage_update` and resolves it with `triage_update_status`. No card matched in our runs (the project has none yet), so this path has not run.

### Entire

- **Checkpoints.** The R1 regression was written by a captured Claude Code session (checkpoint `01M4KBD5VKTNXSMEK8K1RY4VM7`). Rootline's fixer sessions are captured too, and their fix commits carry an `Entire-Checkpoint` trailer.
- **`entire why`.** LOCATE asks which commit, checkpoint, session, agent, model and prompt wrote each changed line. For `patient/config.py:2` it returns the R1 session and its prompt. Evidence: `evidence/entire_why_R1_config.json`, `evidence/entire_why_R1_policy.json`.
- **`checkpoint explain --full`.** EXPLAIN reads the session transcript and checks that the quoted assumption appears in it verbatim.
- **Search and graph.** EXPLAIN runs `entire search` with the failure signature, and LOCATE runs `entire graph search --profile full`. Evidence: `evidence/graph_stats.txt`.
- **Trails and findings.** FIX pushes `rootline/fix-<run_id>`, opens a Trail against the regression branch, and adds a high-severity finding on the guilty line naming the session, checkpoint and prompt. Trails 1–4: https://entire.io/gh/bruce249/rootline/trails/1 through /trails/4.

### cfo.ai

Not started. Unit costs measured from neatlogs are in `business/unit_costs.json` once `rootline costs` has a fully ingested run.

## Build log

### 2026-10-10

- Planned: scaffold, patient, 24-ticket eval, Rootline loop.
- Done in this session: repository files for the patient, evals, tests, and the Rootline loop. API keys are present in local `.env` only.
- Verified: `uv run pytest -q` passed 9 tests. Ticket T01 passed one traced run and issued a refund of 89900 paise, in English, with no contact details in the reply.
- Verified: full baseline on commit `71319f7` was 24/24. Result file: `evals/out/baseline-71319f7-20261010T135708Z.json` (gitignored). An earlier run on `1eed772` was 21/24 because contact-detail tickets were refunded; the system prompt now refuses those without issuing a refund.
- Entire CLI 0.11.4 is installed. Codex and Cursor hooks are enabled. The graph plugin is installed and the default trail runners are in `.entire/runners/`. `entire login` is waiting on browser approval.
- Not done: public GitHub push, seeded regression, EC2, cfo.ai.

### 2026-10-11

**Rootline v1 failed on R1, and its own neatlogs trace showed why.** Run `f43fa9505b8c` on `bench/R1`:

- DETECT passed a `filters={"status": "error"}` argument that the neatlogs MCP does not have. The keyword search therefore matched Rootline's own `detect` trace (`43531b4169e2ebc4f8389a9740b9e3ef`), and the failure signature read "the evidence JSON is empty".
- Every patient trace had an errored LLM span, because `gpt-5` models reject `temperature=0`, so trace status could not separate failures from passes.
- EXPLAIN read the current policy file as the source of truth. The R1 session had rewritten that file from 14 to 30 days, so Rootline blamed the correct baseline commit `1eed772` and "quoted" `No associated Entire checkpoint`.
- Bench v1 (`evidence/bench_v1.md`): commit correct 0/1, quote match 0/1, fix verified 0/1.

**Changes (commits `9e863d0` to the latest commit on main):**

- MCP calls use the real tool arguments. No temperature for `gpt-5` models.
- The harness writes an `eval_check` span, owns tracing setup, and masks PII.
- LOCATE uses `entire why` provenance. EXPLAIN reads the policy from before the suspect commit and flags a session that edited it.
- FIX and VERIFY run in a git worktree. The main harness replays the fix worktree's patient with `--patient-dir`.
- FIX restores a tampered policy, pushes, opens a Trail and adds a finding.
- New GUARD step creates a neatlogs detection.
- The Brain client was removed: Entire 0.11.4 has no `brain` command.

**Verified:**

- `pytest -q`: 23 passed.
- Baseline on main `9014920`: 24/24 (`evals/out/baseline-9014920-20261010T203138Z.json`).
- Replay of the `bench/R1` patient (`8c35f9e`) with the same harness: 20/24. T06, T07, T08 and T18 fail the refund check, for orders delivered 15–30 days ago.
- Rootline v2 runs on `bench/R1`. The latest, `4fba03c6d784`, was COMPLETE in 5.1 minutes with no errors:
  - Commit range `71319f7..8c35f9e`, with one candidate `8c35f9e` at score 1.0.
  - Quote verified in the session transcript, with the policy rewrite flagged.
  - Before 20/24, after 24/24 (fix `aa69c41`).
  - Trail 4 and a finding were created.
  - Rootline's own LLM usage, recorded locally: 2 gpt-5 calls, 6,910 prompt and 3,405 completion tokens.
- The earlier run `d6efd4a8dc53` gave the same result and quoted "use the standard 30 day refund window." exactly.
- Bench v2 (`evidence/bench_v2.md`): commit correct 1/1, quote match 1/1, fix verified 1/1.
- Failure recovery, run `ce0ee866cb90` (`evidence/recovery_ce0ee866cb90.md`):
  - It failed twice on real errors: a hidden ExceptionGroup, then neatlogs `not_enabled` for selective trace context.
  - Each failure was recorded in run state. The client was fixed and the run was finished with `rootline resume`, without repeating completed steps.
  - During FIX, Entire's commit hook waited for a console answer. `commit_linking: always` now prevents that.
- Reports: `evidence/report-<run_id>.html`.

**Still open:**

- Unit costs: at the time of writing, neatlogs search had indexed 0 of the latest run's traces and 8 of 24 replay traces from the run before it, and it counted only one of Rootline's LLM calls in the trace totals. `rootline costs` only writes `business/unit_costs.json` from fully indexed runs, so the file is still null. Rerun `uv run rootline costs` later.
- Only R1 is seeded. R2–R8 and R2R5 are planned.
- cfo.ai, EC2 watch mode, demo video, #neatHack posts.
- This build session itself was not captured by Entire, because `entire` was not on PATH for the Claude Code hooks.

## Demo

Pending. Reproduce the R1 investigation:

```powershell
uv run python -m evals.run_evals --label replay-before --patient-dir <worktree of bench/R1>
uv run rootline investigate --branch bench/R1 --since 24h
uv run rootline report <run_id> --open
```

## Known limitations and next steps

- The Entire CLI lives in `%USERPROFILE%\.local\bin`, which is not on PATH in every shell. Rootline finds it there or through `ENTIRE_BIN`, and adds it to PATH for git and agent hooks. Add it to the user PATH so interactive sessions are also checkpointed.
- neatlogs `get_trace_context` rejects any span filter or clipping option (`not_enabled`), so Rootline reads whole traces.
- neatlogs keyword search truncates long input previews. Rootline reads ticket ids from the leading fields.
- Traces from the first PII mask carry masked git SHAs. Rootline ignores those SHAs.
- Triage write-back needs `NEATLOGS_USER_EMAIL` and a matching neatlogs fix card. Neither exists yet.
- Long tickets T13–T15 put the order id only in the first of 13 messages. With a history window of 10 the agent cannot see that id, so the correct baseline result is no refund.
- Inventory timeouts use SHA-256 of `ticket_id + sku + attempt` instead of Python's salted `hash()`, so retries are stable across processes. The rule is still "timeout when the digest mod 5 is 0".

## Submission

Requirements are published at https://neatlogs.com/hackathon. Submission opens 12 October 2026, 7:00 PM IST, and is made by quoting the official neatlogs post with team, name, project, public repo and demo. Required evidence still outstanding: cfo.ai business plan, demo video, #neatHack posts, and neatlogs trace screenshots. Nothing has been submitted.
