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
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.evaluators.cheap import run_cheap_tier
from app.evaluators.medium import run_medium_tier
from app.model_client import ModelCallError, call_model
from app.models import EvaluatorTier, Execution, Finding, Session, Workload
from app.redis_client import get_ledger, set_ledger
from app.schemas.chat import ChatCompletionRequest, ChatCompletionResponse
from app.seed import DEFAULT_WORKLOAD_ID

router = APIRouter()
logger = logging.getLogger(__name__)

SESSION_TTL = timedelta(minutes=15)
LEDGER_DECAY_FACTOR = 0.7
STRIKE_THRESHOLD = 0.7

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
    x_workload_id: uuid.UUID | None = Header(default=None),
    x_session_id: uuid.UUID | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> ChatCompletionResponse:
    workload = await _resolve_workload(db, x_workload_id)
    session = await _resolve_session(db, x_session_id, workload.workload_id)

    response.headers["X-Workload-Id"] = str(workload.workload_id)
    response.headers["X-Session-Id"] = str(session.session_id)

    blocked = await _run_request_side_interception(db, session, workload, request)
    if blocked is not None:
        blocked.headers["X-Workload-Id"] = str(workload.workload_id)
        blocked.headers["X-Session-Id"] = str(session.session_id)
        return blocked

    try:
        parsed, latency_ms = await call_model(request)
    except ModelCallError as exc:
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
    )
    db.add(execution)
    await db.flush()

    blocked = await _run_response_side_interception(db, session, execution, parsed, workload, request)
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
    """Header absent -> the seeded default. Present -> must already exist."""
    if workload_id is None:
        return await db.get(Workload, DEFAULT_WORKLOAD_ID)

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


async def _run_request_side_interception(
    db: AsyncSession, session: Session, workload: Workload, request: ChatCompletionRequest
) -> JSONResponse | None:
    """Cheap-tier PII/prompt-injection scan on the incoming prompt, per
    forks.md Fork #4. No violation -> None (caller falls through to the
    model path). A violation -> persist Execution + Finding rows, update the
    Redis ledger (Fork #3 math), and return the 403 to send instead of
    calling the model.
    """
    text = "\n".join(message.content for message in request.messages)
    candidates = run_cheap_tier(text)
    if not candidates:
        return None

    execution_risk_score = max(candidate.confidence for candidate in candidates)
    execution = Execution(
        session_id=session.session_id,
        workload_id=workload.workload_id,
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

    ledger = await get_ledger(str(session.session_id))
    ledger["cumulative_risk"] = ledger["cumulative_risk"] * LEDGER_DECAY_FACTOR + execution_risk_score
    for candidate in candidates:
        if candidate.confidence > STRIKE_THRESHOLD:
            ledger["strikes"][candidate.category.value] += 1
    await set_ledger(str(session.session_id), ledger)

    primary = max(candidates, key=lambda candidate: candidate.confidence)
    categories = sorted({candidate.category.value for candidate in candidates})
    return JSONResponse(
        status_code=403,
        content={
            "error": {
                "message": (
                    "Request blocked by ControlPlane: "
                    f"{', '.join(categories)} detected in input."
                ),
                "type": "controlplane_policy_violation",
                "param": None,
                "code": primary.category.value,
            }
        },
    )


async def _run_response_side_interception(
    db: AsyncSession,
    session: Session,
    execution: Execution,
    parsed: ChatCompletionResponse,
    workload: Workload,
    request: ChatCompletionRequest,
) -> JSONResponse | None:
    """Cheap-tier PII/prompt-injection scan on the model's response, per
    forks.md Fork #4 ("input and output are NOT treated differently").
    Reuses the same Execution row 1.4 already created for this call (real
    tokens/latency_ms already set) - a response-side block still had a real
    model call happen, unlike a request-side block. No violation ->
    execution_risk_score=0.0 (evaluated, clean), response releases. A
    violation -> persist Finding rows, set execution_risk_score to the max
    confidence, update the Redis ledger (Fork #3 math), and return the 403
    to send instead of releasing the response.

    When cheap tier is clean, 2.4's medium tier runs next (per Fork #4,
    "if cheap tier is inconclusive -> run medium tier"; cheap tier has no
    graded state, so "inconclusive" is read as "found nothing" here - see
    .agents/prompts/2.4-medium-embedding-stub-plan.md). It is currently a
    stub (real detection deferred to 2.5) that always returns no finding,
    so this call site is exercised on every clean response but never
    changes behavior today.
    """
    response_text = parsed.choices[0].message.content
    candidates = run_cheap_tier(response_text)

    if not candidates:
        context_text = "\n".join(message.content for message in request.messages)
        budget_remaining_ms = workload.latency_budget_ms
        candidates = run_medium_tier(context_text, response_text, budget_remaining_ms)

    if not candidates:
        execution.execution_risk_score = 0.0
        await db.commit()
        return None

    execution.execution_risk_score = max(candidate.confidence for candidate in candidates)
    for candidate in candidates:
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

    ledger = await get_ledger(str(session.session_id))
    ledger["cumulative_risk"] = (
        ledger["cumulative_risk"] * LEDGER_DECAY_FACTOR + execution.execution_risk_score
    )
    for candidate in candidates:
        if candidate.confidence > STRIKE_THRESHOLD:
            ledger["strikes"][candidate.category.value] += 1
    await set_ledger(str(session.session_id), ledger)

    primary = max(candidates, key=lambda candidate: candidate.confidence)
    categories = sorted({candidate.category.value for candidate in candidates})
    return JSONResponse(
        status_code=403,
        content={
            "error": {
                "message": (
                    "Response blocked by ControlPlane: "
                    f"{', '.join(categories)} detected in output."
                ),
                "type": "controlplane_policy_violation",
                "param": None,
                "code": primary.category.value,
            }
        },
    )
