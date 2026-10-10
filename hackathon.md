# Rootline

## Project

Rootline finds the exact reasoning mistake in a coding session that made a production support agent start failing, fixes it, and proves the fix. The patient is a customer-support agent for the fictional tea brand Kettle & Co.

## Team

Heisenberg. Handles to publish are still pending.

## Stack

- Python 3.12, OpenAI (`gpt-5-mini` for the patient, `gpt-5` for Rootline)
- neatlogs SDK and MCP
- Entire checkpoints, search, graph, trails (CLI login still pending)
- Codex as the headless fixer
- cfo.ai business plan, not started
- AWS EC2 in us-east-1, not started. Team allowance is $25. One instance, Hackathon_VPC, t3.small, when the watch demo is ready.

## Build log

### 2026-10-10

- Planned: scaffold, patient, 24-ticket eval, Rootline loop.
- Done in this session: repository files for the patient, evals, tests, and the Rootline loop. API keys are present in local `.env` only.
- Verified: `uv run pytest -q` passed 9 tests. Ticket T01 passed one traced run and issued a refund of 89900 paise, in English, with no contact details in the reply.
- Verified: full baseline on commit `71319f7` was 24/24. Result file: `evals/out/baseline-71319f7-20261010T135708Z.json` (gitignored). An earlier run on `1eed772` was 21/24 because contact-detail tickets were refunded; the system prompt now refuses those without issuing a refund.
- Entire CLI 0.11.4 is installed. Codex and Cursor hooks are enabled. The graph plugin is installed and the default trail runners are in `.entire/runners/`. `entire login` is waiting on browser approval.
- Not done: public GitHub push, seeded regression, EC2, cfo.ai.

## Demo

Pending.

## Known limitations and next steps

- Entire is not installed in this shell, so checkpoints, graph, and trails cannot run yet.
- The public GitHub repo is not created yet. The logged-in `gh` account is `bruce249`. Confirm that account before pushing.
- Long tickets T13–T15 put the order id only in the first of 13 messages. With a history window of 10 the agent cannot see that id, so the correct baseline result is no refund.
- Inventory timeouts use SHA-256 of `ticket_id + sku + attempt` instead of Python's salted `hash()`, so retries are stable across processes. The rule is still "timeout when the digest mod 5 is 0".
- No cost figures yet. `business/unit_costs.json` stays null until a real run.

## Submission

Requirements are published at https://neatlogs.com/hackathon. Submission opens 12 October 2026, 7:00 PM IST. Nothing has been submitted.
