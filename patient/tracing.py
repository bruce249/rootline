from __future__ import annotations

import os
import re

import neatlogs
from dotenv import load_dotenv

_client = None
_started = False

# Alphanumeric boundaries, so ten digits at the start of a git SHA are not a phone number.
_PHONE = re.compile(r"(?<![0-9A-Za-z+])(?:\+91[\s-]?)?[6-9]\d{9}(?![0-9A-Za-z])")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def redact_text(text: str) -> str:
    return _EMAIL.sub("[email]", _PHONE.sub("[phone]", text))


def redact_pii(value):
    """Mask phone numbers and emails before a span leaves the process.

    lookup_order returns customer contact details on purpose (the policy, not the
    tool, protects them), so without this mask they would be stored in neatlogs.
    """
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {key: redact_pii(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_pii(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_pii(item) for item in value)
    return value


def init_patient():
    """Initialise neatlogs, then wrap the OpenAI client. Import OpenAI only after init."""
    global _client, _started
    if _started:
        return _client
    load_dotenv()
    neatlogs.init(
        api_key=os.environ["NEATLOGS_API_KEY"],
        workflow_name="support-ticket",
        tags=["patient", "kettle-co"],
        mask=redact_pii,
    )
    from openai import OpenAI

    _client = neatlogs.wrap(OpenAI())
    _started = True
    return _client


def get_client():
    return init_patient()
