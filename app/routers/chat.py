"""POST /v1/chat/completions - the OpenAI-compatible proxy entry point.

1.2 (this milestone) resolves X-Workload-Id/X-Session-Id against Postgres:
workload lookup (fallback to DEFAULT_WORKLOAD_ID), session lookup-or-create
(fallback to a fresh length-1 session). No evaluators (1.3), no real model
call (1.4) yet. See .agents/prompts/1.2-workload-session-resolution-plan.md.
"""

import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Session, Workload
from app.schemas.chat import ChatCompletionRequest, ChatCompletionResponse, Choice, ChatMessage, Usage
from app.seed import DEFAULT_WORKLOAD_ID

router = APIRouter()

SESSION_TTL = timedelta(minutes=15)


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
