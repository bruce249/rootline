Fix the Kettle & Co. support agent in this repository. Change as little as possible. Only edit files under patient/. Do not touch tests, evals or rootline. Do not run the evals; Rootline replays them after you finish.

Commit {{ bad_commit }} broke the agent. The coding session that produced it acted on this assumption:

"{{ assumption_quote }}"

Why that assumption is wrong:
{{ why_wrong }}

Source of truth:
{{ source_of_truth }}

What must be restored:
{{ restore }}
{% if policy_tampered %}
That session also rewrote patient/policy/refund_policy.md to match its change. Rootline has already restored the policy file to the text below. Do not edit the policy file. Make the code and configuration agree with it.
{% else %}
The policy file is correct. Do not edit it.
{% endif %}
Policy (source of truth):
{{ policy_before }}

Failing tickets from neatlogs traces:
{{ failing_tickets }}

Previous attempt failures:
{{ previous_failures }}

Keep these behaviours: refunds use the policy window and integer paise; a refund above the escalation threshold is escalated, not refunded; never put a customer's phone number or email in a reply; reply in the customer's language; keep inventory retries.

When you are done, reply with one sentence naming the files you changed.
