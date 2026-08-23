"""Async Redis client for the session ledger (Upstash).

Reads REDIS_URL from the environment (see .env). This Upstash database is
shared with another project, so every key here is prefixed KEY_PREFIX to
avoid collisions. The ledger's actual aggregation math (decay, strike
windows, escalation) lives in Phase 3; this module only stores and
retrieves it, per forks.md Fork #3.
"""

import json
import os
from typing import Any

from dotenv import load_dotenv
from redis.asyncio import Redis

load_dotenv()

REDIS_URL = os.environ["REDIS_URL"]

redis_client = Redis.from_url(REDIS_URL, decode_responses=True)

KEY_PREFIX = "controlplane:"
LEDGER_TTL_SECONDS = 15 * 60

STRIKE_CATEGORIES = (
    "pii",
    "hallucination",
    "toxicity",
    "bias",
    "prompt_injection",
    "custom_policy",
)


def _ledger_key(session_id: str) -> str:
    return f"{KEY_PREFIX}session:{session_id}:ledger"


def default_ledger() -> dict[str, Any]:
    return {
        "cumulative_risk": 0.0,
        "strikes": {category: 0 for category in STRIKE_CATEGORIES},
    }


async def get_ledger(session_id: str) -> dict[str, Any]:
    raw = await redis_client.get(_ledger_key(session_id))
    if raw is None:
        return default_ledger()
    return json.loads(raw)


async def set_ledger(session_id: str, ledger: dict[str, Any]) -> None:
    await redis_client.set(_ledger_key(session_id), json.dumps(ledger), ex=LEDGER_TTL_SECONDS)
