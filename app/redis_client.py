"""Async Redis client for the session ledger (Upstash).

Reads REDIS_URL from the environment (see .env). This Upstash database is
shared with another project, so every key here is prefixed KEY_PREFIX to
avoid collisions. The ledger's aggregation math (decay, strike-window
expiry) lives here per forks.md Fork #3; apply_ledger_update() is the one
place chat.py should touch to read or mutate a session's ledger - see
.agents/prompts/3.1-ledger-update-logic-plan.md. Escalation (deciding to
block on the ledger's state) is still Phase 3.2's job, not this module's.
"""

import json
import os
import time
from typing import Any

from dotenv import load_dotenv
from redis.asyncio import Redis
from redis.exceptions import WatchError

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

LEDGER_DECAY_FACTOR = 0.7
STRIKE_THRESHOLD = 0.7
# Fork #3: "only strikes from the last 5 turns OR last 2 minutes count" -
# read as union (ratified with the user): a strike survives until it is
# BOTH more than 5 turns old AND more than 2 minutes old.
STRIKE_WINDOW_TURNS = 5
STRIKE_WINDOW_SECONDS = 120

# Fork #3's exact escalation trigger: cumulative_risk > 0.7 OR any
# strikes[category] >= 3. See .agents/prompts/3.2-escalation-check-plan.md -
# is_escalated() is a pure predicate, never touches Redis itself; callers
# supply an already-read-or-updated ledger.
ESCALATION_RISK_THRESHOLD = 0.7
ESCALATION_STRIKE_COUNT = 3

# 7.1/M2: apply_ledger_update's WATCH/MULTI/EXEC retries against a
# concurrent writer on the same key before giving up. Contention this high
# would mean something else is badly wrong (this is bounded so a pathological
# case can't hang forever), not a value tuned against real load.
LEDGER_UPDATE_MAX_RETRIES = 10


def _ledger_key(session_id: str) -> str:
    return f"{KEY_PREFIX}session:{session_id}:ledger"


def default_ledger() -> dict[str, Any]:
    return {
        "cumulative_risk": 0.0,
        "turn": 0,
        "strikes": {category: 0 for category in STRIKE_CATEGORIES},
        "strike_events": {category: [] for category in STRIKE_CATEGORIES},
    }


def _upgrade_ledger(ledger: dict[str, Any]) -> dict[str, Any]:
    """Old ledgers (pre-3.1) have no turn/strike_events - .setdefault() them
    in place so a blob written before this shipped doesn't crash a read.
    """
    ledger.setdefault("turn", 0)
    ledger.setdefault("strike_events", {category: [] for category in STRIKE_CATEGORIES})
    return ledger


async def get_ledger(session_id: str) -> dict[str, Any]:
    raw = await redis_client.get(_ledger_key(session_id))
    if raw is None:
        return default_ledger()
    return _upgrade_ledger(json.loads(raw))


async def set_ledger(session_id: str, ledger: dict[str, Any]) -> None:
    await redis_client.set(_ledger_key(session_id), json.dumps(ledger), ex=LEDGER_TTL_SECONDS)


def _prune_and_count(events: list[dict[str, Any]], current_turn: int, now_ts: float) -> tuple[list[dict[str, Any]], int]:
    live = [
        event
        for event in events
        if (current_turn - event["turn"] < STRIKE_WINDOW_TURNS)
        or (now_ts - event["ts"] < STRIKE_WINDOW_SECONDS)
    ]
    return live, len(live)


async def apply_ledger_update(
    session_id: str,
    execution_risk_score: float,
    strikes_input: list[tuple[str, float]],
    *,
    is_new_turn: bool = True,
    turn_anchor: int | None = None,
    ts_anchor: float | None = None,
) -> dict[str, Any]:
    """The one place a session's ledger is read, mutated, and written back.

    Decays cumulative_risk per Fork #3's exact math every call (including a
    clean turn at execution_risk_score=0.0, so risk actually fades over a
    session instead of freezing after the last violation). Bumps `turn`
    only when is_new_turn (the async expensive-tier task always passes
    False, so it can never corrupt the strike window for the rest of the
    session - see the 3.1 spec's Rationale). A new strike is stamped with
    turn_anchor/ts_anchor when given (the async task's late-arriving
    finding is stamped at the ORIGINAL request's turn/time, not whenever
    the background task happens to finish), else the live turn/now. Pruning
    itself always compares against the ledger's live turn/time, never an
    anchor - only a strike's own stamp is ever anchored.

    7.1/M2: the read-modify-write is wrapped in a WATCH/MULTI/EXEC
    optimistic-locking transaction, not a plain GET-then-SET. The async
    expensive-tier task (_run_expensive_tier_task) is *designed* to run
    concurrently with the caller's next turn on the same session - a plain
    GET/SET here meant last-writer-wins, silently dropping whichever update
    lost the race (a real hallucination strike, or a new turn's decay/strike,
    vanishing with no error). WatchError (someone else wrote between our GET
    and our EXEC) retries the whole read-modify-write with a fresh read,
    bounded at LEDGER_UPDATE_MAX_RETRIES. See
    docs/reviews/2026-08-25-phase6.md Major #2,
    .agents/prompts/7.1-review-fixes-plan.md.
    """
    key = _ledger_key(session_id)
    async with redis_client.pipeline(transaction=True) as pipe:
        for _ in range(LEDGER_UPDATE_MAX_RETRIES):
            try:
                await pipe.watch(key)
                raw = await pipe.get(key)
                ledger = _upgrade_ledger(json.loads(raw)) if raw is not None else default_ledger()
                now_ts = time.time()

                ledger["cumulative_risk"] = ledger["cumulative_risk"] * LEDGER_DECAY_FACTOR + execution_risk_score
                if is_new_turn:
                    ledger["turn"] += 1

                stamp_turn = turn_anchor if turn_anchor is not None else ledger["turn"]
                stamp_ts = ts_anchor if ts_anchor is not None else now_ts
                for category, confidence in strikes_input:
                    if confidence > STRIKE_THRESHOLD:
                        ledger["strike_events"][category].append({"turn": stamp_turn, "ts": stamp_ts})

                for category in STRIKE_CATEGORIES:
                    live, count = _prune_and_count(ledger["strike_events"][category], ledger["turn"], now_ts)
                    ledger["strike_events"][category] = live
                    ledger["strikes"][category] = count

                pipe.multi()
                pipe.set(key, json.dumps(ledger), ex=LEDGER_TTL_SECONDS)
                await pipe.execute()
                return ledger
            except WatchError:
                continue

    raise RuntimeError(f"apply_ledger_update: too much contention on session {session_id}")


def is_escalated(ledger: dict[str, Any]) -> bool:
    """Fork #3's exact escalation condition. Pure predicate - does not read
    or write Redis; the caller supplies an already-current ledger (a fresh
    get_ledger() peek, or the dict apply_ledger_update() just returned).
    """
    if ledger["cumulative_risk"] > ESCALATION_RISK_THRESHOLD:
        return True
    return any(count >= ESCALATION_STRIKE_COUNT for count in ledger["strikes"].values())
