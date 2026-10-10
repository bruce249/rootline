You are investigating why a production support agent regressed. You get failing trace evidence from neatlogs, the diff of a suspect commit, Entire's line provenance (which coding-agent session, prompt and model wrote each changed line), and the transcript of that session.

Find the single instruction or belief in the session that introduced the regression, and quote it exactly as it appears in the transcript or the session prompt. Prefer the agent's own reasoning (for example a belief it states about what is "standard" or "safe") when it exists; otherwise quote the instruction it followed.

The source of truth is the policy as it stood BEFORE the commit (`policy_before_commit`). If `commit_edits_source_of_truth` is true, the session rewrote the policy to match its change. Treat that as part of the mistake: the policy file is not evidence that the change was right.

Explain why the assumption conflicts with the source of truth and how it produces the failing traces. Do not guess beyond the evidence.

Return only JSON:

{"commit":"", "file":"", "assumption_quote":"", "why_wrong":"", "source_of_truth":"", "restore":"", "confidence":0.0}

- file: the file whose change caused the failure.
- source_of_truth: quote the line from `policy_before_commit` that the change violates.
- restore: one sentence saying what must be put back, with exact values.
- confidence: 0 to 1.
