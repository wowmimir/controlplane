"""POST /v1/chat/completions - the OpenAI-compatible proxy entry point.

1.2 resolves X-Workload-Id/X-Session-Id against Postgres. 1.3 (this
milestone) runs cheap-tier evaluators (PII, prompt injection) against the
incoming prompt before any model call: a violation writes a Finding, updates
the Redis session ledger (Fork #3 math), and returns a 403 without ever
reaching the model. No real model call (1.4) yet - a clean prompt still
falls through to the stub response. See
.agents/prompts/1.3-request-side-interception-plan.md.
"""

import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.evaluators.cheap import run_cheap_tier
from app.models import EvaluatorTier, Execution, Finding, Session, Workload
from app.redis_client import get_ledger, set_ledger
from app.schemas.chat import ChatCompletionRequest, ChatCompletionResponse, Choice, ChatMessage, Usage
from app.seed import DEFAULT_WORKLOAD_ID

router = APIRouter()

SESSION_TTL = timedelta(minutes=15)
LEDGER_DECAY_FACTOR = 0.7
STRIKE_THRESHOLD = 0.7


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

    return ChatCompletionResponse(
        id=f"chatcmpl-stub-{uuid.uuid4()}",
        object="chat.completion",
        created=int(time.time()),
        model=request.model,
        choices=[
            Choice(
                index=0,
                message=ChatMessage(
                    role="assistant",
                    content=(
                        "ControlPlane stub response - model forwarding is not "
                        "implemented yet (Phase 1.4). Resolved workload_id="
                        f"{workload.workload_id}, session_id={session.session_id}."
                    ),
                ),
                finish_reason="stop",
            )
        ],
        usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
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
                evidence_ref=candidate.evidence_ref,
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
