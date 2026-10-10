from __future__ import annotations

import os

import neatlogs
from dotenv import load_dotenv

_client = None
_started = False


def init_rootline():
    global _client, _started
    if _started:
        return _client
    load_dotenv()
    neatlogs.init(
        api_key=os.environ["NEATLOGS_API_KEY"],
        workflow_name="rootline-investigation",
        tags=["rootline"],
    )
    from openai import OpenAI

    _client = neatlogs.wrap(OpenAI())
    _started = True
    return _client


def get_client():
    return init_rootline()
