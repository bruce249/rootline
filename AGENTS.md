# Agent notes

Rootline investigates the Kettle & Co. support agent in `patient/`.

- The refund policy in `patient/policy/refund_policy.md` is the source of truth.
- Amounts are integer paise. The refund window and escalation threshold live in `patient/config.py`.
- Do not put secrets in the repo. `.env` stays untracked.
- Code under `rootline/` must not read ground-truth files.
- A seeded regression may edit `patient/` only. Do not "fix" a regression branch back to the policy unless you are Rootline's fixer, working from trace evidence.
