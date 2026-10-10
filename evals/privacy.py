from __future__ import annotations

import re

_PHONE = re.compile(r"(?:\+91[\s-]?)?(?<!\d)[6-9]\d{9}(?!\d)")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def redact_pii(value):
    """Mask phone numbers and emails in a span before it is exported."""
    if isinstance(value, str):
        return _EMAIL.sub("[email]", _PHONE.sub("[phone]", value))
    if isinstance(value, dict):
        return {key: redact_pii(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_pii(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_pii(item) for item in value)
    return value
