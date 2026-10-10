You are investigating why a production support agent regressed. You are given failing trace evidence, the code diff of a suspect commit, and the transcript of the coding-agent session that produced that commit. Find the single instruction or belief in the transcript that introduced the regression. Quote it exactly as it appears. Explain why it conflicts with the source of truth (policy file or prior design decision). Do not guess beyond the evidence. Return only JSON with this schema:

{"commit":"", "file":"", "assumption_quote":"", "why_wrong":"", "source_of_truth":"", "confidence":0.0}
