from __future__ import annotations

import json
import os
from pathlib import Path

import neatlogs
from dotenv import load_dotenv

from rootline.tracing import get_client

_PROMPTS = Path(__file__).resolve().parents[1] / "prompts"


def read_prompt(name: str) -> str:
    return (_PROMPTS / name).read_text(encoding="utf-8")


def parse_json(text: str) -> dict:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0]
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start : end + 1]
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("model JSON was not an object")
    return parsed


@neatlogs.span(kind="AGENT", name="rootline-llm")
def complete(system: str, user: str) -> str:
    load_dotenv()
    client = get_client()
    model = os.environ.get("ROOTLINE_MODEL") or "gpt-5"
    kwargs = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    try:
        response = client.chat.completions.create(**kwargs)
    except Exception as exc:
        if "temperature" not in str(exc).lower():
            raise
        kwargs.pop("temperature")
        response = client.chat.completions.create(**kwargs)
    return (response.choices[0].message.content or "").strip()
