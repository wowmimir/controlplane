"""POST /v1/chat/completions - the OpenAI-compatible proxy entry point.

1.2 resolves X-Workload-Id/X-Session-Id against Postgres. 1.3 runs
cheap-tier evaluators (PII, prompt injection) against the incoming prompt
before any model call: a violation writes a Finding, updates the Redis
session ledger (Fork #3 math), and returns a 403 without ever reaching the
model. 1.4 forwards a clean prompt to the real model API (Ollama,
OpenAI-compatible, see app/model_client.py); a model-call failure returns
502 unconditionally - never routed through Workload.fail_mode, which is
Phase 3.3's job for ControlPlane's own internal errors. 1.5 (this
milestone) runs the same cheap-tier evaluators against the model's
response before it releases to the caller: a violation reuses the
Execution row 1.4 already created (real tokens/latency_ms, since the model
call already happened), writes Finding(s), updates the ledger, and returns
403 instead of releasing the response. See
.agents/prompts/1.5-response-side-interception-plan.md.
"""

import logging
import random
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session, get_db
from app.evaluators.cheap import run_cheap_tier
from app.evaluators.expensive import run_expensive_tier
from app.evaluators.medium import run_medium_tier
from app.evaluators.types import FindingCandidate
from app.model_client import ModelCallError, call_model
from app.models import (
    Disposition,
    EvaluatorTier,
    Execution,
    FailMode,
    Finding,
    PolicyProfile,
    Session,
    Workload,
)
from app.redis_client import apply_ledger_update, get_ledger, is_escalated
from app.schemas.chat import ChatCompletionRequest, ChatCompletionResponse
from app.seed import DEFAULT_WORKLOAD_ID

router = APIRouter()
logger = logging.getLogger(__name__)

SESSION_TTL = timedelta(minutes=15)

# 8.1: a fast-profile workload's async LLM-judge (2.5) samples instead of
# running on every clean response - the judge is async/post-release so
# skipping it saves inference cost, not latency, and fast is the profile
# assigned to cost-sensitive, high-volume use cases. Fixed rate, not derived
# from Workload.cost_budget_per_request's actual value (no real per-call
# dollar cost exists for a local Ollama backend) - see
# .agents/prompts/8.1-policy-profile-enforcement-plan.md.
FAST_TIER_JUDGE_SAMPLE_RATE = 0.10

# Caller-facing text per ModelCallError.code - deliberately generic. The
# real detail (raw upstream error body, MODEL_API_BASE_URL) goes to the
# server log only; echoing it to an unauthenticated caller would leak
# internal topology today and, once MODEL_API_BASE_URL points at a real
# hosted provider, upstream org/billing/quota details too.
_MODEL_ERROR_MESSAGES = {
    "model_unreachable": "the upstream model API was unreachable",
    "model_api_error": "the upstream model API returned an error",
    "model_response_invalid": "the upstream model API returned a response ControlPlane could not parse",
}


@router.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    response: Response,
    background_tasks: BackgroundTasks,
    x_workload_id: uuid.UUID | None = Header(default=None),
    x_session_id: uuid.UUID | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> ChatCompletionResponse:
    workload = await _resolve_workload(db, x_workload_id)
    session = await _resolve_session(db, x_session_id, workload.workload_id)

    response.headers["X-Workload-Id"] = str(workload.workload_id)
    response.headers["X-Session-Id"] = str(session.session_id)

    try:
        blocked, request_flags = await _run_request_side_interception(db, session, workload, request)
    except Exception:
        logger.error(
            "request-side interception failed for session %s", session.session_id, exc_info=True
        )
        blocked = _internal_error_response() if workload.fail_mode == FailMode.fail_closed else None
        request_flags = []
    if blocked is not None:
        blocked.headers["X-Workload-Id"] = str(workload.workload_id)
        blocked.headers["X-Session-Id"] = str(session.session_id)
        return blocked

    call_start = time.perf_counter()
    try:
        parsed, latency_ms = await call_model(request)
    except ModelCallError as exc:
        # 4.2: an attempted-but-failed model call still gets an audit trail
        # row - tokens/execution_risk_score stay None (no usable response),
        # latency_ms is elapsed wall-clock time up to the failure. Without
        # this, a request-side-clean request whose model call then fails
        # left zero Postgres rows. See
        # .agents/prompts/4.2-execution-persistence-plan.md.
        failed_execution = Execution(
            session_id=session.session_id,
            workload_id=workload.workload_id,
            latency_ms=round((time.perf_counter() - call_start) * 1000),
            retries=0,
            tool_loop_count=0,
            # 8.2: a fast-profile request-side flag is real regardless of
            # whether the model call then succeeded - it still gets logged
            # against this turn's Execution row.
            disposition=Disposition.flagged if request_flags else Disposition.clean,
        )
        db.add(failed_execution)
        await db.flush()
        for candidate in request_flags:
            db.add(
                Finding(
                    execution_id=failed_execution.execution_id,
                    category=candidate.category,
                    confidence=candidate.confidence,
                    evaluator_tier=EvaluatorTier.cheap,
                    evidence_ref={"side": "request", **(candidate.evidence_ref or {})},
                )
            )
        await db.commit()

        error_response = _model_error_response(exc)
        error_response.headers["X-Workload-Id"] = str(workload.workload_id)
        error_response.headers["X-Session-Id"] = str(session.session_id)
        return error_response

    execution = Execution(
        session_id=session.session_id,
        workload_id=workload.workload_id,
        tokens=parsed.usage.total_tokens,
        latency_ms=latency_ms,
        retries=0,
        tool_loop_count=0,
        # 8.2: a deferred fast-profile request-side flag attaches to THIS
        # row (the one real Execution for this model-call attempt), never a
        # second standalone row - see _run_request_side_interception.
        disposition=Disposition.flagged if request_flags else Disposition.clean,
    )
    db.add(execution)
    # 7.1/M1: commit immediately, not just flush - this row must exist in
    # Postgres regardless of what happens in response-side interception
    # below. Previously this only flushed (assigning execution_id) and
    # committed for the first time inside _run_response_side_interception;
    # an exception raised before that commit (e.g. run_cheap_tier throwing)
    # rolled the flushed INSERT back under fail_open, releasing a real model
    # response with zero audit trace. Every later
    # execution.execution_risk_score = ...; await db.commit() is now a plain
    # UPDATE on an already-durable row. See docs/reviews/2026-08-25-phase6.md
    # Major #1, .agents/prompts/7.1-review-fixes-plan.md.
    await db.flush()
    for candidate in request_flags:
        db.add(
            Finding(
                execution_id=execution.execution_id,
                category=candidate.category,
                confidence=candidate.confidence,
                evaluator_tier=EvaluatorTier.cheap,
                evidence_ref={"side": "request", **(candidate.evidence_ref or {})},
            )
        )
    await db.commit()

    try:
        blocked = await _run_response_side_interception(
            db, session, execution, parsed, workload, request, background_tasks
        )
    except Exception:
        logger.error(
            "response-side interception failed for session %s", session.session_id, exc_info=True
        )
        blocked = _internal_error_response() if workload.fail_mode == FailMode.fail_closed else None
    if blocked is not None:
        blocked.headers["X-Workload-Id"] = str(workload.workload_id)
        blocked.headers["X-Session-Id"] = str(session.session_id)
        return blocked

    return parsed


def _model_error_response(exc: ModelCallError) -> JSONResponse:
    """Model-call failure -> 502 (upstream gateway failure), OpenAI-style
    envelope. Distinct from 1.2's 400 (caller misconfiguration) and 1.3's
    403 (policy block). Deliberately NOT routed through Workload.fail_mode
    - that's Phase 3.3's job; a model-API failure here always surfaces as
    this same 502, regardless of the workload's fail_open/fail_closed
    setting. The caller-facing message is a fixed, generic string per
    exc.code (_MODEL_ERROR_MESSAGES) - the real detail (raw upstream body,
    MODEL_API_BASE_URL) is logged server-side only, never echoed to an
    unauthenticated caller.
    """
    logger.error("model call failed (code=%s): %s", exc.code, exc.message)
    message = _MODEL_ERROR_MESSAGES.get(exc.code, "the model call failed")
    return JSONResponse(
        status_code=502,
        content={
            "error": {
                "message": f"ControlPlane could not complete the model call: {message}",
                "type": "controlplane_upstream_error",
                "param": None,
                "code": exc.code,
            }
        },
    )


async def _resolve_workload(db: AsyncSession, workload_id: uuid.UUID | None) -> Workload:
    """Header absent -> the seeded default. Present -> must already exist.

    7.1/N9: the default lookup used to return db.get(...)'s result directly,
    which is None if the seeded default row is ever missing (seed failed, or
    the row was deleted directly in the database) - the caller immediately
    dereferences workload.workload_id, producing a raw 500. Mirrors the
    explicit-id branch's existing None-check, but as a 503 (ControlPlane
    misconfiguration) rather than a 400 (caller error).
    """
    if workload_id is None:
        workload = await db.get(Workload, DEFAULT_WORKLOAD_ID)
        if workload is None:
            raise HTTPException(status_code=503, detail="Default workload is not seeded")
        return workload

    workload = await db.get(Workload, workload_id)
    if workload is None:
        raise HTTPException(status_code=400, detail=f"Unknown workload_id: {workload_id}")
    return workload


async def _resolve_session(
    db: AsyncSession, session_id: uuid.UUID | None, workload_id: uuid.UUID
) -> Session:
    """Absent -> create a fresh (length-1) session. Present -> create at that
    id if new, reuse if it already belongs to this workload, else reject
    (a Session cannot span two workloads, per forks.md Fork #1).
    """
    ttl_expires_at = datetime.now(timezone.utc) + SESSION_TTL

    session = await db.get(Session, session_id) if session_id is not None else None

    if session is None:
        session = Session(
            session_id=session_id or uuid.uuid4(),
            workload_id=workload_id,
            ttl_expires_at=ttl_expires_at,
        )
        db.add(session)
    elif session.workload_id != workload_id:
        raise HTTPException(
            status_code=400,
            detail=(
                f"session_id {session_id} belongs to workload "
                f"{session.workload_id}, not {workload_id}"
            ),
        )
    else:
        session.ttl_expires_at = ttl_expires_at

    await db.commit()
    await db.refresh(session)
    return session


def _policy_block_response(side: Literal["request", "response"], candidates: list[FindingCandidate]) -> JSONResponse:
    """The 403 envelope shared by a request-side and a response-side block
    (forks.md Fork #4: "input and output are NOT treated differently").
    Extracted in 3.1 to remove the duplication between the two interception
    functions below; byte-identical output to what each used to build
    inline, just parameterized by which side triggered it.
    """
    primary = max(candidates, key=lambda candidate: candidate.confidence)
    categories = sorted({candidate.category.value for candidate in candidates})
    verb, noun = ("Request", "input") if side == "request" else ("Response", "output")
    return JSONResponse(
        status_code=403,
        content={
            "error": {
                "message": f"{verb} blocked by ControlPlane: {', '.join(categories)} detected in {noun}.",
                "type": "controlplane_policy_violation",
                "param": None,
                "code": primary.category.value,
            }
        },
    )


def _internal_error_response() -> JSONResponse:
    """A ControlPlane-internal failure (Redis, Postgres, or evaluator code)
    on a fail_closed workload -> 503. Distinct type/code from
    _model_error_response (502, the upstream MODEL API failed) and from
    _policy_block_response/_escalation_block_response (403, a real policy
    decision was made) - this means ControlPlane itself could not complete
    its own evaluation. The real exception is logged server-side only (see
    the call sites in chat_completions); this body is always the same
    fixed, generic message. See
    .agents/prompts/3.3-fail-open-fail-closed-handling-plan.md.
    """
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "message": "ControlPlane encountered an internal error while evaluating this request.",
                "type": "controlplane_internal_error",
                "param": None,
                "code": "internal_error",
            }
        },
    )


def _escalation_block_response() -> JSONResponse:
    """Session-level block: the ledger's accumulated state (not this turn's
    own content) tripped Fork #3's escalation condition
    (cumulative_risk > 0.7 OR any strikes[category] >= 3). Distinct
    type/code from _policy_block_response so logs/audits and any
    client-side handling can tell "session in cooldown" apart from "this
    content was blocked". See
    .agents/prompts/3.2-escalation-check-plan.md.
    """
    return JSONResponse(
        status_code=403,
        content={
            "error": {
                "message": (
                    "This session is temporarily blocked: accumulated risk has "
                    "exceeded ControlPlane's policy threshold. It will clear "
                    "automatically as recent activity ages out."
                ),
                "type": "controlplane_session_escalated",
                "param": None,
                "code": "session_escalated",
            }
        },
    )


async def _sync_session_ledger(db: AsyncSession, session: Session, ledger: dict) -> None:
    """4.3: mirror the Redis ledger's cumulative_risk/strikes into Postgres's
    Session row (its own schema comment already claims to be "the durable
    copy of the ledger" - this is what makes that true). Called right after
    every apply_ledger_update call.

    Deliberately best-effort: wrapped in its own try/except that always
    logs and swallows, never routed through the workload's fail_mode. A
    mirror-write failure happens strictly after Redis (and any Finding/
    Execution rows) already recorded the real decision - letting it flip
    that decision under fail_open, or 503 an otherwise-clean turn under
    fail_closed, would be a strictly worse outcome than a stale Postgres
    value. Ratified with the user. See
    .agents/prompts/4.3-session-ledger-durability-plan.md.
    """
    try:
        session.cumulative_risk = ledger["cumulative_risk"]
        session.strikes = ledger["strikes"]
        await db.commit()
    except Exception:
        logger.error(
            "session ledger Postgres sync failed for session %s", session.session_id, exc_info=True
        )


async def _safe_ledger_update(
    db: AsyncSession,
    session: Session,
    execution_risk_score: float,
    strikes_input: list[tuple[str, float]],
    **kwargs,
) -> dict | None:
    """7.1/M1: a block decision, once made (and for two of its three callers,
    already committed to Postgres as an Execution/Finding), must survive a
    later Redis/Postgres ledger-write failure - the caller still returns its
    already-decided 403 either way. Without this, an exception here
    propagated out of the calling interception function to
    chat_completions's outer try/except, which under fail_open falls through
    to call_model and creates a SECOND Execution row for the same turn (the
    request-side violation branch), or under fail_closed replaces an already
    -correct 403 with a misleading 503 (the escalation branch, which has
    nothing to lose from a failed cooldown touch). See
    docs/reviews/2026-08-25-phase6.md Major #1,
    .agents/prompts/7.1-review-fixes-plan.md.
    """
    try:
        ledger = await apply_ledger_update(str(session.session_id), execution_risk_score, strikes_input, **kwargs)
        await _sync_session_ledger(db, session, ledger)
        return ledger
    except Exception:
        logger.error(
            "ledger update failed for session %s (block decision already final)",
            session.session_id,
            exc_info=True,
        )
        return None


async def _run_request_side_interception(
    db: AsyncSession, session: Session, workload: Workload, request: ChatCompletionRequest
) -> tuple[JSONResponse | None, list[FindingCandidate]]:
    """Cheap-tier PII/prompt-injection scan on the incoming prompt, per
    forks.md Fork #4. Returns (blocked_response, flagged_candidates) -
    exactly one of the two is ever non-empty/non-None:
      - Clean: (None, []) - caller falls through to the model path.
      - strict/balanced hit, or an already-escalated session: persist
        Execution + Finding rows (or, for escalation, an Execution row with
        no Finding - see below), update the Redis ledger (Fork #3 math, per
        .agents/prompts/3.1-ledger-update-logic-plan.md), and return the 403
        to send instead of calling the model: (response, []).
      - 8.2: a fast-profile hit: do NOT stop the turn (the model still gets
        called, matching Fork #4's "flag for review" tier) and do NOT create
        a standalone Execution row here (would violate the established "one
        Execution row per real model-call attempt" invariant, 1.5/4.2) - the
        ledger still updates now (flagging is still a real signal), and the
        candidates travel back to chat_completions to attach as Finding rows
        on the real Execution row it creates once the model call concludes:
        (None, candidates). See
        .agents/prompts/8.2-tiered-decision-logic-plan.md.

    3.2: before any of that, a read-only peek at the session's CURRENT
    ledger checks whether it is already escalated from prior turns (Fork
    #3: cumulative_risk > threshold OR any strikes[category] >= count, per
    8.1's per-profile thresholds). If so, this turn's content is never
    scanned at all (ratified with the user - fail fast, matching the
    existing cheap-tier philosophy applied one layer earlier) - it blocks
    immediately, with a single zero-risk decay touch so the session can cool
    down over subsequent turns. 8.2: this early return also now creates an
    Execution row (disposition=blocked, execution_risk_score=None - the
    ledger's raw cumulative_risk is unbounded and would corrupt this
    column's 0-1 max-confidence meaning; there is still no per-turn content
    to attach a Finding to, so none is written), where before this milestone
    it created nothing at all (a known console-invisibility gap). A
    NOT-escalated session is never touched here (get_ledger, not
    apply_ledger_update) - the touch only happens on this early-return path,
    which is that request's sole conclusion, preserving 3.1's
    one-touch-per-request invariant. See
    .agents/prompts/3.2-escalation-check-plan.md,
    .agents/prompts/8.2-tiered-decision-logic-plan.md.
    """
    ledger = await get_ledger(str(session.session_id))
    if is_escalated(ledger, workload.policy_profile):
        escalation_execution = Execution(
            session_id=session.session_id,
            workload_id=workload.workload_id,
            disposition=Disposition.blocked,
            execution_risk_score=None,
        )
        db.add(escalation_execution)
        await db.commit()
        await _safe_ledger_update(db, session, 0.0, [])
        return _escalation_block_response(), []

    # 8.0: scan only the newest turn, not the full resent history - a real
    # OpenAI-shaped client resends the whole conversation on every request,
    # so joining all of request.messages here re-triggers a fresh
    # Finding/strike on old content still present in later turns. See
    # .agents/prompts/8.0-fix-request-side-full-history-rescan-plan.md.
    text = request.messages[-1].content if request.messages else ""
    candidates = run_cheap_tier(text)
    if not candidates:
        return None, []

    execution_risk_score = max(candidate.confidence for candidate in candidates)
    strikes_input = [(candidate.category.value, candidate.confidence) for candidate in candidates]

    if workload.policy_profile == PolicyProfile.fast:
        # Flagged: no standalone row here - chat_completions attaches these
        # candidates to the real Execution row once the model call
        # concludes (success or failure alike).
        await _safe_ledger_update(db, session, execution_risk_score, strikes_input)
        return None, candidates

    # strict/balanced: unchanged from before this milestone, plus the new
    # disposition field.
    execution = Execution(
        session_id=session.session_id,
        workload_id=workload.workload_id,
        disposition=Disposition.blocked,
        execution_risk_score=execution_risk_score,
    )
    db.add(execution)
    await db.flush()

    for candidate in candidates:
        db.add(
            Finding(
                execution_id=execution.execution_id,
                category=candidate.category,
                confidence=candidate.confidence,
                evaluator_tier=EvaluatorTier.cheap,
                evidence_ref={"side": "request", **(candidate.evidence_ref or {})},
            )
        )
    await db.commit()

    await _safe_ledger_update(db, session, execution_risk_score, strikes_input)

    return _policy_block_response("request", candidates), []


def _maybe_schedule_expensive_tier(
    background_tasks: BackgroundTasks,
    execution_id: uuid.UUID,
    session_id: uuid.UUID,
    context_text: str,
    response_text: str,
    workload: Workload,
    ledger: dict | None,
    ts_anchor: float,
) -> None:
    """8.2: shared by every response-side branch that has a real model
    response to judge (clean, flagged, blocked) - the async judge is
    decision-independent (Fork #4: it can only update the ledger/audit
    trail post-release, never block or alter what already went out), so it
    was only ever gated by "did control flow reach the bottom of the clean
    branch," an accident of the original control flow, not a deliberate
    exclusion. Never called from the escalation short-circuit, per Fork
    #4's "do not run medium/expensive tier" once escalation trips.

    ledger is None when the preceding _safe_ledger_update call itself
    failed - there is no reliable turn/timestamp anchor in that case, so
    this turn's judge scheduling is skipped rather than guessed. See
    .agents/prompts/8.2-tiered-decision-logic-plan.md.
    """
    if ledger is None:
        return
    # 8.1: fast-profile workloads sample the async judge instead of running
    # it on every response, to give cost_budget_per_request's
    # cost-sensitivity story a real effect; strict/balanced schedule it
    # every time, unchanged from before that milestone.
    should_sample_judge = (
        workload.policy_profile != PolicyProfile.fast
        or random.random() < FAST_TIER_JUDGE_SAMPLE_RATE
    )
    if not should_sample_judge:
        return
    background_tasks.add_task(
        _run_expensive_tier_task,
        execution_id=execution_id,
        session_id=session_id,
        context_text=context_text,
        response_text=response_text,
        turn_anchor=ledger["turn"],
        ts_anchor=ts_anchor,
    )


async def _run_response_side_interception(
    db: AsyncSession,
    session: Session,
    execution: Execution,
    parsed: ChatCompletionResponse,
    workload: Workload,
    request: ChatCompletionRequest,
    background_tasks: BackgroundTasks,
) -> JSONResponse | None:
    """Cheap-tier PII/prompt-injection scan on the model's response, per
    forks.md Fork #4 ("input and output are NOT treated differently").
    Reuses the same Execution row 1.4 already created for this call (real
    tokens/latency_ms already set) - a response-side block/flag still had a
    real model call happen, unlike a request-side block. No violation ->
    disposition=clean, execution_risk_score=0.0, response releases. A
    violation -> persist Finding rows, set execution_risk_score to the max
    confidence, update the Redis ledger (Fork #3 math), and either return
    the 403 (strict/balanced: disposition=blocked) or release the response
    as None/200 (fast: disposition=flagged - 8.2's "flag for review" tier,
    see .agents/prompts/8.2-tiered-decision-logic-plan.md).

    When cheap tier is clean, 2.4's medium tier runs next (per Fork #4,
    "if cheap tier is inconclusive -> run medium tier"; cheap tier has no
    graded state, so "inconclusive" is read as "found nothing" here - see
    .agents/prompts/2.4-medium-embedding-stub-plan.md). It is a permanent
    stub that always returns no finding (real hallucination detection lives
    in the expensive tier instead, per the 2.4 correction), so every
    cheap-tier-clean response reaches the branch below.

    2.5/8.2: the expensive tier (LLM-as-judge) is scheduled via
    BackgroundTasks to run *after* release, from every branch that has a
    real response to judge (clean, flagged, blocked - see
    _maybe_schedule_expensive_tier), since forks.md Fork #4 caps its
    post-release power at updating the ledger/audit trail - it can never
    block or alter this response, so it doesn't matter which disposition
    this turn landed on.

    3.1: this is where a clean turn's ledger touch lives (per
    .agents/prompts/3.1-ledger-update-logic-plan.md) - the one point in the
    whole request where a request-side-clean call's turn concludes
    synchronously, so cumulative_risk decays even when nothing was found.
    The turn/timestamp that touch produces is threaded into the scheduled
    background task as turn_anchor/ts_anchor, so if the expensive tier finds
    something later, that strike is stamped as having happened at THIS
    turn, not whenever the judge call finishes.
    """
    response_text = parsed.choices[0].message.content
    # Deliberately still the full joined history, unlike the 8.0 fix to
    # _run_request_side_interception's cheap-tier scan: this never feeds
    # run_cheap_tier (medium tier is a permanent no-op stub), it only
    # grounds the async expensive-tier judge, which benefits from full
    # conversation context. Ratified scope cut, not an oversight - see
    # .agents/prompts/8.0-fix-request-side-full-history-rescan-plan.md.
    context_text = "\n".join(message.content for message in request.messages)
    cheap_candidates = run_cheap_tier(response_text)

    if cheap_candidates:
        # 8.2: strict/balanced keep hard-blocking exactly as before this
        # milestone; fast flags instead - the response still releases, but
        # the hit is logged (real Finding, real ledger update) for review.
        disposition = (
            Disposition.flagged if workload.policy_profile == PolicyProfile.fast else Disposition.blocked
        )
        execution.disposition = disposition
        execution.execution_risk_score = max(candidate.confidence for candidate in cheap_candidates)
        for candidate in cheap_candidates:
            db.add(
                Finding(
                    execution_id=execution.execution_id,
                    category=candidate.category,
                    confidence=candidate.confidence,
                    evaluator_tier=EvaluatorTier.cheap,
                    evidence_ref={"side": "response", **(candidate.evidence_ref or {})},
                )
            )
        await db.commit()

        ts_anchor = time.time()
        ledger = await _safe_ledger_update(
            db,
            session,
            execution.execution_risk_score,
            [(candidate.category.value, candidate.confidence) for candidate in cheap_candidates],
        )
        _maybe_schedule_expensive_tier(
            background_tasks, execution.execution_id, session.session_id,
            context_text, response_text, workload, ledger, ts_anchor,
        )

        if disposition == Disposition.blocked:
            return _policy_block_response("response", cheap_candidates)
        return None  # flagged: release the already-computed response as 200

    # 3.2: per Fork #4's literal ordering - cheap tier's result feeds
    # the ledger -> check escalation -> only THEN decide whether medium
    # tier runs at all. This turn's own content was clean, but the
    # session's accumulated state might already be over threshold from
    # prior turns; if so, block here and never reach medium/expensive
    # tier. See .agents/prompts/3.2-escalation-check-plan.md.
    #
    # 8.2: deliberately NOT setting execution.disposition = clean here -
    # this row's disposition may already be `flagged` (a fast-profile
    # request-side hit chat_completions attached to this same row before
    # response-side interception ran) and this response-side-clean branch
    # must never downgrade that back to clean. Disposition only ever moves
    # clean -> flagged/blocked, or flagged -> blocked (never backwards).
    # Found and fixed during this milestone's self-check (a real bug: a
    # fast-profile request-side flag was silently erased whenever the
    # response side then came back clean).
    execution.execution_risk_score = 0.0
    await db.commit()

    ts_anchor = time.time()
    # Deliberately the unwrapped apply_ledger_update, not _safe_ledger_update
    # - per 7.1's own rationale, no decision is final yet at this point, so
    # a failure here should correctly fall through to 3.3's fail_open/
    # fail_closed handling rather than being swallowed.
    ledger = await apply_ledger_update(str(session.session_id), 0.0, [])
    await _sync_session_ledger(db, session, ledger)

    if is_escalated(ledger, workload.policy_profile):
        # 8.2: this Execution row already exists (real tokens/latency_ms
        # from the completed model call, committed above) - unlike the
        # request-side escalation path, no new row is needed, only the
        # disposition label. execution_risk_score stays 0.0 (this turn's
        # own content really was clean; the session's accumulated state is
        # what tripped, not this turn).
        execution.disposition = Disposition.blocked
        await db.commit()
        return _escalation_block_response()

    budget_remaining_ms = workload.latency_budget_ms
    medium_candidates = run_medium_tier(context_text, response_text, budget_remaining_ms)

    if not medium_candidates:
        _maybe_schedule_expensive_tier(
            background_tasks, execution.execution_id, session.session_id,
            context_text, response_text, workload, ledger, ts_anchor,
        )
        return None

    # Medium-tier-violation branch: currently unreachable (2.4's stub
    # always returns []), kept for structural completeness. See
    # .agents/prompts/3.2-escalation-check-plan.md Follow-up - medium
    # tier becoming real will need its own escalation re-check design.
    disposition = (
        Disposition.flagged if workload.policy_profile == PolicyProfile.fast else Disposition.blocked
    )
    execution.disposition = disposition
    execution.execution_risk_score = max(candidate.confidence for candidate in medium_candidates)
    for candidate in medium_candidates:
        db.add(
            Finding(
                execution_id=execution.execution_id,
                category=candidate.category,
                confidence=candidate.confidence,
                evaluator_tier=EvaluatorTier.medium,
                evidence_ref={"side": "response", **(candidate.evidence_ref or {})},
            )
        )
    await db.commit()

    ledger = await _safe_ledger_update(
        db,
        session,
        execution.execution_risk_score,
        [(candidate.category.value, candidate.confidence) for candidate in medium_candidates],
    )
    _maybe_schedule_expensive_tier(
        background_tasks, execution.execution_id, session.session_id,
        context_text, response_text, workload, ledger, ts_anchor,
    )

    if disposition == Disposition.blocked:
        return _policy_block_response("response", medium_candidates)
    return None


async def _run_expensive_tier_task(
    execution_id: uuid.UUID,
    session_id: uuid.UUID,
    context_text: str,
    response_text: str,
    turn_anchor: int,
    ts_anchor: float,
) -> None:
    """BackgroundTasks entry point for 2.5's LLM-as-judge, scheduled from
    _run_response_side_interception only after the response has already
    been committed and released. Runs on its own DB session (async_session,
    not the request-scoped Depends(get_db) session, which is already closed
    by the time BackgroundTasks fires) - per forks.md Fork #4, this can only
    update the ledger and audit trail, never the response the caller
    already received.

    A clean verdict (run_expensive_tier returns []) touches nothing, same
    "clean = no ledger write" precedent 1.3/1.5 already set. Any exception
    anywhere in this function is caught and logged, never re-raised - there
    is no caller left to report an error to. See
    .agents/prompts/2.5-expensive-llm-as-judge-plan.md.

    3.1: is_new_turn=False always - this task must never advance the
    ledger's turn counter (it would corrupt the strike window for every
    later check this session), and any strike it writes is stamped with
    turn_anchor/ts_anchor (the original request's clean-path touch), not
    whenever this task happens to finish. This does mean the same turn's
    cumulative_risk can decay twice (once synchronously at 0.0, once again
    here for real) - an accepted, self-correcting quirk, not a bug; see
    .agents/prompts/3.1-ledger-update-logic-plan.md's Rationale.

    8.2: since the judge can now also fire after a flagged/blocked cheap-tier
    hit (not only after a clean turn), execution.execution_risk_score may
    already be non-zero when this task runs. The ledger's own synchronous
    touch for that hit already contributed the cheap-tier score as its own
    decay+add event - this call must contribute only the judge's OWN new
    score (judge_score) as this event's contribution, never the cheap+judge
    merged value, or the cheap-tier's contribution would be double-counted
    into cumulative_risk. execution.execution_risk_score itself (the
    Postgres column, Fork #2's "max confidence across all Findings in that
    execution") is separately updated to the max of whatever it already was
    and judge_score.
    """
    try:
        candidates = await run_expensive_tier(context_text, response_text)
        if not candidates:
            return

        judge_score = max(candidate.confidence for candidate in candidates)

        async with async_session() as db:
            execution = await db.get(Execution, execution_id)
            execution.execution_risk_score = max(execution.execution_risk_score or 0.0, judge_score)
            for candidate in candidates:
                db.add(
                    Finding(
                        execution_id=execution_id,
                        category=candidate.category,
                        confidence=candidate.confidence,
                        evaluator_tier=EvaluatorTier.expensive,
                        evidence_ref={"side": "response", **(candidate.evidence_ref or {})},
                    )
                )
            await db.commit()

            ledger = await apply_ledger_update(
                str(session_id),
                judge_score,
                [(candidate.category.value, candidate.confidence) for candidate in candidates],
                is_new_turn=False,
                turn_anchor=turn_anchor,
                ts_anchor=ts_anchor,
            )

            # 4.3: this task never receives a Session ORM object (only a
            # raw session_id) - fetch it here, inside the same DB scope
            # already open for the Execution/Finding writes above, rather
            # than opening a third session.
            session_row = await db.get(Session, session_id)
            await _sync_session_ledger(db, session_row, ledger)
    except Exception:
        logger.error("expensive-tier background task failed for execution %s", execution_id, exc_info=True)
