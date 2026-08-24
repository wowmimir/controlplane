"""Console API (/api/console/...).

GET /summary: read-only dashboard aggregates. Per
.agents/prompts/5.1-dashboard-plan.md: total_requests/blocked_count are
all-time Postgres counts. blocked_count excludes Executions whose only
Finding(s) are evaluator_tier=expensive - 2.5's async judge can only update
the ledger/audit trail post-release (Fork #4), it never actually blocks
anything. Escalation blocks (3.2) write no Postgres row at all (Redis-only,
15-min TTL, no durable history), so they cannot be counted here by any
query; the console UI shows a caveat about that gap instead of silently
over- or under-claiming.

GET/POST /workloads, PATCH /workloads/{workload_id}: workload management
(list/create/edit), per .agents/prompts/5.2-workload-management-view-plan.md
and forks.md Fork #1's "console requires a workload management view"
requirement. No delete - matches STATUS.md's literal "list/create/edit"
scope. workload_id is always server-generated (the model's own uuid4
default); the seeded default workload is editable like any other row.

GET /sessions, GET /sessions/{session_id}: session drilldown, per
.agents/prompts/5.3-session-drilldown-plan.md. Reads Postgres exclusively,
never Redis - Redis's ledger has a 15-minute TTL and cannot answer "what
happened historically," while Session/Execution/Finding in Postgres are the
durable audit trail (4.1-4.3). `escalated` reuses is_escalated()
(app.redis_client) verbatim against the session's Postgres-sourced
{cumulative_risk, strikes} rather than re-deriving Fork #3's threshold
check. Per-execution `blocked` reuses get_summary's own
evaluator_tier != expensive definition.

GET /feed: live feed, per .agents/prompts/5.4-live-feed-plan.md. The 25 most
recent Executions across ALL sessions/workloads (not scoped to one session,
unlike /sessions), polled by the console every ~3s - a flat most-recent-N
query, no `since` cursor (demo traffic volume doesn't need one, per the
spec's Rationale). `blocked`/`categories` reuse the same
evaluator_tier != expensive rule as /summary and /sessions/{id}. Escalation
blocks still write no Execution row, so they never appear here either - the
same accepted gap already documented on /summary and /sessions/{id}.
"""

import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import EvaluatorTier, Execution, Finding, Session, Workload
from app.redis_client import is_escalated
from app.schemas.console import (
    CategoryCount,
    DashboardSummary,
    ExecutionOut,
    FeedEntry,
    FindingOut,
    SessionDetail,
    SessionSummary,
    TimeBucket,
    WorkloadCreate,
    WorkloadOut,
    WorkloadUpdate,
)

SESSION_LIST_LIMIT = 50
FEED_LIMIT = 25


def _workload_name(workload: Workload | None) -> str | None:
    if workload is None or not workload.metadata_:
        return None
    return workload.metadata_.get("name")


def _is_blocked(findings: list[Finding]) -> bool:
    return any(finding.evaluator_tier != EvaluatorTier.expensive for finding in findings)

router = APIRouter(prefix="/api/console")

OVER_TIME_WINDOW = timedelta(hours=24)


def _to_workload_out(workload: Workload) -> WorkloadOut:
    return WorkloadOut(
        workload_id=workload.workload_id,
        policy_profile=workload.policy_profile,
        fail_mode=workload.fail_mode,
        latency_budget_ms=workload.latency_budget_ms,
        cost_budget_per_request=workload.cost_budget_per_request,
        metadata=workload.metadata_,
        created_at=workload.created_at,
    )


@router.get("/summary")
async def get_summary(db: AsyncSession = Depends(get_db)) -> DashboardSummary:
    total_requests = await db.scalar(select(func.count(Execution.execution_id))) or 0

    blocked_count = (
        await db.scalar(
            select(func.count(func.distinct(Execution.execution_id)))
            .select_from(Execution)
            .join(Finding, Finding.execution_id == Execution.execution_id)
            .where(Finding.evaluator_tier != EvaluatorTier.expensive)
        )
        or 0
    )

    category_rows = await db.execute(select(Finding.category, func.count()).group_by(Finding.category))
    findings_by_category = [
        CategoryCount(category=category.value, count=count) for category, count in category_rows.all()
    ]

    window_start = datetime.now(timezone.utc) - OVER_TIME_WINDOW

    total_bucket_rows = await db.execute(
        select(
            func.date_trunc("hour", Execution.created_at).label("bucket"),
            func.count(Execution.execution_id).label("total"),
        )
        .where(Execution.created_at >= window_start)
        .group_by("bucket")
    )
    totals_by_bucket = {row.bucket: row.total for row in total_bucket_rows.all()}

    blocked_bucket_rows = await db.execute(
        select(
            func.date_trunc("hour", Execution.created_at).label("bucket"),
            func.count(func.distinct(Execution.execution_id)).label("blocked"),
        )
        .select_from(Execution)
        .join(Finding, Finding.execution_id == Execution.execution_id)
        .where(
            Execution.created_at >= window_start,
            Finding.evaluator_tier != EvaluatorTier.expensive,
        )
        .group_by("bucket")
    )
    blocked_by_bucket = {row.bucket: row.blocked for row in blocked_bucket_rows.all()}

    all_buckets = sorted(set(totals_by_bucket) | set(blocked_by_bucket))
    over_time = [
        TimeBucket(
            bucket=bucket,
            total=totals_by_bucket.get(bucket, 0),
            blocked=blocked_by_bucket.get(bucket, 0),
        )
        for bucket in all_buckets
    ]

    return DashboardSummary(
        total_requests=total_requests,
        blocked_count=blocked_count,
        findings_by_category=findings_by_category,
        over_time=over_time,
    )


@router.get("/workloads")
async def list_workloads(db: AsyncSession = Depends(get_db)) -> list[WorkloadOut]:
    rows = await db.execute(select(Workload).order_by(Workload.created_at))
    return [_to_workload_out(workload) for workload in rows.scalars().all()]


@router.post("/workloads", status_code=201)
async def create_workload(
    body: WorkloadCreate, db: AsyncSession = Depends(get_db)
) -> WorkloadOut:
    workload = Workload(
        policy_profile=body.policy_profile,
        fail_mode=body.fail_mode,
        latency_budget_ms=body.latency_budget_ms,
        cost_budget_per_request=body.cost_budget_per_request,
        metadata_=body.metadata,
    )
    db.add(workload)
    await db.commit()
    await db.refresh(workload)
    return _to_workload_out(workload)


@router.patch("/workloads/{workload_id}")
async def update_workload(
    workload_id: uuid.UUID, body: WorkloadUpdate, db: AsyncSession = Depends(get_db)
) -> WorkloadOut:
    workload = await db.get(Workload, workload_id)
    if workload is None:
        raise HTTPException(status_code=404, detail="Workload not found")

    updates = body.model_dump(exclude_unset=True)
    if "metadata" in updates:
        workload.metadata_ = updates.pop("metadata")
    for field, value in updates.items():
        setattr(workload, field, value)

    await db.commit()
    await db.refresh(workload)
    return _to_workload_out(workload)


@router.get("/sessions")
async def list_sessions(db: AsyncSession = Depends(get_db)) -> list[SessionSummary]:
    rows = await db.execute(
        select(Session, Workload)
        .join(Workload, Workload.workload_id == Session.workload_id)
        .order_by(Session.created_at.desc())
        .limit(SESSION_LIST_LIMIT)
    )
    sessions_with_workload = rows.all()
    session_ids = [session.session_id for session, _ in sessions_with_workload]

    count_rows = await db.execute(
        select(Execution.session_id, func.count(Execution.execution_id))
        .where(Execution.session_id.in_(session_ids))
        .group_by(Execution.session_id)
    )
    execution_counts = {session_id: count for session_id, count in count_rows.all()}

    return [
        SessionSummary(
            session_id=session.session_id,
            workload_id=session.workload_id,
            workload_name=_workload_name(workload),
            cumulative_risk=session.cumulative_risk,
            strikes=session.strikes,
            escalated=is_escalated(
                {"cumulative_risk": session.cumulative_risk, "strikes": session.strikes}
            ),
            execution_count=execution_counts.get(session.session_id, 0),
            ttl_expires_at=session.ttl_expires_at,
            created_at=session.created_at,
        )
        for session, workload in sessions_with_workload
    ]


@router.get("/sessions/{session_id}")
async def get_session_detail(
    session_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> SessionDetail:
    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    workload = await db.get(Workload, session.workload_id)

    execution_rows = await db.execute(
        select(Execution)
        .where(Execution.session_id == session_id)
        .order_by(Execution.created_at)
    )
    executions = execution_rows.scalars().all()
    execution_ids = [execution.execution_id for execution in executions]

    findings_by_execution: dict[uuid.UUID, list[Finding]] = defaultdict(list)
    if execution_ids:
        finding_rows = await db.execute(
            select(Finding)
            .where(Finding.execution_id.in_(execution_ids))
            .order_by(Finding.timestamp)
        )
        for finding in finding_rows.scalars().all():
            findings_by_execution[finding.execution_id].append(finding)

    execution_outs = [
        ExecutionOut(
            execution_id=execution.execution_id,
            tokens=execution.tokens,
            latency_ms=execution.latency_ms,
            retries=execution.retries,
            tool_loop_count=execution.tool_loop_count,
            execution_risk_score=execution.execution_risk_score,
            blocked=_is_blocked(findings_by_execution[execution.execution_id]),
            created_at=execution.created_at,
            findings=[
                FindingOut(
                    finding_id=finding.finding_id,
                    category=finding.category.value,
                    confidence=finding.confidence,
                    evaluator_tier=finding.evaluator_tier.value,
                    evidence_ref=finding.evidence_ref,
                    timestamp=finding.timestamp,
                )
                for finding in findings_by_execution[execution.execution_id]
            ],
        )
        for execution in executions
    ]

    return SessionDetail(
        session_id=session.session_id,
        workload_id=session.workload_id,
        workload_name=_workload_name(workload),
        cumulative_risk=session.cumulative_risk,
        strikes=session.strikes,
        escalated=is_escalated(
            {"cumulative_risk": session.cumulative_risk, "strikes": session.strikes}
        ),
        execution_count=len(executions),
        ttl_expires_at=session.ttl_expires_at,
        created_at=session.created_at,
        executions=execution_outs,
    )


@router.get("/feed")
async def get_feed(db: AsyncSession = Depends(get_db)) -> list[FeedEntry]:
    rows = await db.execute(
        select(Execution, Session, Workload)
        .join(Session, Session.session_id == Execution.session_id)
        .join(Workload, Workload.workload_id == Session.workload_id)
        .order_by(Execution.created_at.desc())
        .limit(FEED_LIMIT)
    )
    executions_with_context = rows.all()
    execution_ids = [execution.execution_id for execution, _, _ in executions_with_context]

    findings_by_execution: dict[uuid.UUID, list[Finding]] = defaultdict(list)
    if execution_ids:
        finding_rows = await db.execute(
            select(Finding).where(Finding.execution_id.in_(execution_ids))
        )
        for finding in finding_rows.scalars().all():
            findings_by_execution[finding.execution_id].append(finding)

    return [
        FeedEntry(
            execution_id=execution.execution_id,
            session_id=execution.session_id,
            workload_id=execution.workload_id,
            workload_name=_workload_name(workload),
            tokens=execution.tokens,
            latency_ms=execution.latency_ms,
            execution_risk_score=execution.execution_risk_score,
            blocked=_is_blocked(findings_by_execution[execution.execution_id]),
            categories=sorted(
                {finding.category.value for finding in findings_by_execution[execution.execution_id]}
            ),
            created_at=execution.created_at,
        )
        for execution, _, workload in executions_with_context
    ]
