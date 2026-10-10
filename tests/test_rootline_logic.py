from __future__ import annotations

import json
import re

from evals.privacy import redact_pii as harness_redact
from patient.tracing import redact_pii
from rootline.steps.detect import row_passed, scoreboard, verdict_from_spans, window_start
from rootline.steps.explain import quote_ok
from rootline.steps.guard import guard_spec
from rootline.steps.locate import changed_lines


def test_window_start_parses_relative_windows():
    assert window_start("last_24h") < window_start("1h")
    assert window_start("7d") < window_start("24h")
    assert window_start("nonsense").endswith("Z")


def test_row_verdicts_from_search_rows():
    passed = {"output_preview": '{"ticket_id": "T01", "passed": true}', "status": "error"}
    failed = {"output_preview": "Your refund has been processed.", "status": "error"}
    unknown = {"output_preview": "hello", "status": "success"}
    assert row_passed(passed) is True
    assert row_passed(failed) is False
    assert row_passed(unknown) is None


def test_eval_check_span_is_the_verdict():
    spans = [
        {"name": "support-ticket", "is_root": True, "status": "ERROR"},
        {"name": "eval_check", "output_value": json.dumps({"passed": False, "failed_checks": ["refund"]})},
    ]
    assert verdict_from_spans(spans) == {"passed": False, "failed_checks": ["refund"]}
    legacy = [{"name": "support-ticket", "is_root": True, "status": "ERROR", "error": "failed_checks=['refund', 'lang']"}]
    assert verdict_from_spans(legacy) == {"passed": False, "failed_checks": ["refund", "lang"]}


def test_scoreboard_keeps_latest_verdict_per_ticket():
    def row(ticket, out, at, status="success"):
        return {"input_preview": json.dumps({"ticket_id": ticket}), "output_preview": out, "created_at": at, "status": status}

    rows = [
        row("T06", "refunded", "2026-10-10T01", status="error"),
        row("T06", '{"passed": true}', "2026-10-10T02"),
        row("T07", "refunded", "2026-10-10T02", status="error"),
    ]
    board = scoreboard(rows)
    assert board["passed"] == 1 and board["total"] == 2


def test_changed_lines_reads_new_side_numbers():
    diff = (
        "diff --git a/patient/config.py b/patient/config.py\n"
        "--- a/patient/config.py\n+++ b/patient/config.py\n"
        "@@ -2 +2 @@\n-REFUND_WINDOW_DAYS = 14\n+REFUND_WINDOW_DAYS = 30\n"
        "--- a/patient/policy/refund_policy.md\n+++ b/patient/policy/refund_policy.md\n"
        "@@ -5,0 +6,2 @@\n+line a\n+line b\n"
    )
    assert changed_lines(diff) == [
        {"file": "patient/config.py", "line": 2, "text": "REFUND_WINDOW_DAYS = 30"},
        {"file": "patient/policy/refund_policy.md", "line": 6, "text": "line a"},
        {"file": "patient/policy/refund_policy.md", "line": 7, "text": "line b"},
    ]


def test_quote_must_be_verbatim_modulo_whitespace():
    transcript = "[user]: Update the support agent to use the\n  standard 30 day refund window."
    assert quote_ok("use the standard 30 day refund window", transcript)
    assert not quote_ok("use a 30 day window", transcript)
    assert not quote_ok("", transcript)


def test_guard_regex_matches_eval_check_output():
    pattern = re.compile(guard_spec("refund")["config"]["output_pattern"], re.I)
    assert pattern.search('{"ticket_id":"T06","passed":false,"failed_checks":["refund"]}')
    assert pattern.search('{"failed_checks": ["lang", "refund"]}')
    assert not pattern.search('{"failed_checks":[]}')
    assert not pattern.search('{"failed_checks":["lang"]}')


def test_pii_is_masked_before_export():
    span = {"output": '{"phone":"9888881008","email":"arjun.rao@example.com"}', "attrs": ["+91 9833331003"], "n": 3}
    masked = redact_pii(span)
    text = json.dumps(masked)
    assert "9888881008" not in text and "arjun.rao@example.com" not in text and "9833331003" not in text
    assert masked["n"] == 3
    assert "139900" in redact_pii("amount 139900 paise")


def test_harness_mask_matches_patient_mask():
    sample = {"a": "call 9811111001 or ananya.shah@example.com", "b": ["+91 9833331003"]}
    assert harness_redact(sample) == redact_pii(sample)
