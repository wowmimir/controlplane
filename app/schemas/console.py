"""Schemas for the console API (/api/console/...).

Per .agents/prompts/5.1-dashboard-plan.md and
.agents/prompts/5.2-workload-management-view-plan.md - plain
pydantic.BaseModel subclasses, same convention as schemas/chat.py.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import FailMode, PolicyProfile, ReviewStatus


class CategoryCount(BaseModel):
    category: str
    count: int


class TimeBucket(BaseModel):
    bucket: datetime
    total: int
    blocked: int


class DashboardSummary(BaseModel):
    total_requests: int
    blocked_count: int
    findings_by_category: list[CategoryCount]
    over_time: list[TimeBucket]
    # 8.4: p50/p95 of Execution.governance_overhead_ms over rows that have a
    # measured value (the full sync-pipeline turns). null on a fresh DB.
    governance_overhead_p50_ms: float | None
    governance_overhead_p95_ms: float | None
    # 8.3: the trust metric. `reviewed_findings` = confirmed + false_positive
    # (unreviewed excluded); `false_positive_rate` = false_positive /
    # reviewed_findings, or null when nothing has been reviewed. Labeled "of
    # reviewed findings" in the console so an unreviewed backlog can't read as
    # a misleading ~0%.
    reviewed_findings: int
    false_positive_findings: int
    false_positive_rate: float | None


class WorkloadOut(BaseModel):
    workload_id: uuid.UUID
    policy_profile: PolicyProfile
    fail_mode: FailMode
    latency_budget_ms: int
    cost_budget_per_request: float | None
    metadata: dict | None
    created_at: datetime


class WorkloadCreate(BaseModel):
    policy_profile: PolicyProfile
    fail_mode: FailMode
    latency_budget_ms: int = Field(gt=0)
    cost_budget_per_request: float | None = Field(default=None, ge=0)
    metadata: dict | None = None


class WorkloadUpdate(BaseModel):
    policy_profile: PolicyProfile | None = None
    fail_mode: FailMode | None = None
    latency_budget_ms: int | None = Field(default=None, gt=0)
    cost_budget_per_request: float | None = Field(default=None, ge=0)
    metadata: dict | None = None


class SessionSummary(BaseModel):
    session_id: uuid.UUID
    workload_id: uuid.UUID
    workload_name: str | None
    cumulative_risk: float
    strikes: dict
    escalated: bool
    execution_count: int
    ttl_expires_at: datetime
    created_at: datetime


class FindingOut(BaseModel):
    finding_id: uuid.UUID
    category: str
    confidence: float
    evaluator_tier: str
    evidence_ref: dict | None
    timestamp: datetime
    # 8.3: operator judgment - unreviewed / confirmed / false_positive.
    review_status: str


class FindingReviewUpdate(BaseModel):
    """8.3: body of PATCH /api/console/findings/{finding_id}. Any of the three
    values is accepted, and any transition is allowed (including back to
    unreviewed)."""

    review_status: ReviewStatus


class ReviewQueueEntry(BaseModel):
    """8.3: one row of GET /api/console/findings - a finding plus enough
    context to review it without opening its session."""

    finding_id: uuid.UUID
    category: str
    confidence: float
    evaluator_tier: str
    pattern: str | None
    side: str | None
    masked_excerpt: str | None
    review_status: str
    execution_id: uuid.UUID
    disposition: str
    session_id: uuid.UUID
    workload_id: uuid.UUID
    workload_name: str | None
    timestamp: datetime


class DetectionHealthPattern(BaseModel):
    """8.3: one detection pattern's review outcomes, aggregated across every
    workload. `pattern` is `evidence_ref->>'pattern'` for cheap-tier findings,
    or `<category>:<tier>` for findings without one (the expensive-tier judge)."""

    pattern: str
    category: str
    confirmed: int
    false_positive: int
    unreviewed: int
    reviewed: int
    false_positive_rate: float | None
    needs_attention: bool
    suppressed_by: list[uuid.UUID]


class ExecutionOut(BaseModel):
    execution_id: uuid.UUID
    tokens: int | None
    latency_ms: int | None
    retries: int
    tool_loop_count: int
    execution_risk_score: float | None
    disposition: str
    model: str | None
    governance_overhead_ms: int | None
    created_at: datetime
    findings: list[FindingOut]


class SessionDetail(SessionSummary):
    executions: list[ExecutionOut]


class FeedEntry(BaseModel):
    execution_id: uuid.UUID
    session_id: uuid.UUID
    workload_id: uuid.UUID
    workload_name: str | None
    tokens: int | None
    latency_ms: int | None
    execution_risk_score: float | None
    disposition: str
    model: str | None
    categories: list[str]
    created_at: datetime
