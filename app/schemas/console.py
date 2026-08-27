"""Schemas for the console API (/api/console/...).

Per .agents/prompts/5.1-dashboard-plan.md and
.agents/prompts/5.2-workload-management-view-plan.md - plain
pydantic.BaseModel subclasses, same convention as schemas/chat.py.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import FailMode, PolicyProfile


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
