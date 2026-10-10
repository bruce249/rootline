# Recovery evidence: Rootline run ce0ee866cb90

One investigation of `bench/R1` that failed twice on real external errors, was fixed, and finished with `rootline resume` from the saved state. Every row is copied from `.rootline/runs/ce0ee866cb90/state.json`.

| Time (UTC) | Step | What failed |
|---|---|---|
| 2026-10-10T20:32:29 | DETECT | unhandled errors in a TaskGroup (1 sub-exception) |
| 2026-10-10T20:32:33 | DETECT | unhandled errors in a TaskGroup (1 sub-exception) |
| 2026-10-10T20:32:39 | DETECT | unhandled errors in a TaskGroup (1 sub-exception) |
| 2026-10-10T20:32:39 | DETECT | unhandled errors in a TaskGroup (1 sub-exception) |
| 2026-10-10T20:34:44 | DETECT | get_trace_context: {"error":"Selective trace context is disabled until the NL-1924 preview-column migration and API-first rollout are verified","errorCode":"not |
| 2026-10-10T20:34:50 | DETECT | get_trace_context: {"error":"Selective trace context is disabled until the NL-1924 preview-column migration and API-first rollout are verified","errorCode":"not |
| 2026-10-10T20:34:57 | DETECT | get_trace_context: {"error":"Selective trace context is disabled until the NL-1924 preview-column migration and API-first rollout are verified","errorCode":"not |
| 2026-10-10T20:35:09 | DETECT | get_trace_context: {"error":"Selective trace context is disabled until the NL-1924 preview-column migration and API-first rollout are verified","errorCode":"not |
| 2026-10-10T20:35:09 | DETECT | get_trace_context: {"error":"Selective trace context is disabled until the NL-1924 preview-column migration and API-first rollout are verified","errorCode":"not |

Resumed at: 2026-10-10T20:34:32Z, 2026-10-10T20:35:31Z
Final status: **COMPLETE** after steps DETECT, LOCATE, EXPLAIN, FIX, VERIFY, GUARD, REPORT.

What Rootline did next each time:
1. First launch: a neatlogs MCP call in DETECT failed inside an anyio ExceptionGroup that hid the cause. Rootline retried 3 times, recorded each error in state, and stopped with status FAILED. The client now unwraps the real error and backs off longer.
2. First resume: the real error surfaced. `get_trace_context` with a clipping option counts as a selective request, which neatlogs rejects with `not_enabled`. The client now requests whole traces.
3. Second resume: DETECT through REPORT finished. During FIX, Entire's commit hook waited for a console answer. The hook was stopped, the commit went through, and `commit_linking: always` now prevents the prompt.

Logs: `recovery_ce0ee866cb90_.log`, `recovery_ce0ee866cb90__resume.log`, `recovery_ce0ee866cb90__resume2.log`.
