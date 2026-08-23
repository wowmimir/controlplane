import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, Integer
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db import Base
from app.models.enums import FailMode, PolicyProfile


class Workload(Base):
    __tablename__ = "workload"

    workload_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    policy_profile: Mapped[PolicyProfile] = mapped_column(
        Enum(PolicyProfile, name="policy_profile"), nullable=False
    )
    latency_budget_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_budget_per_request: Mapped[float | None] = mapped_column(Float, nullable=True)
    fail_mode: Mapped[FailMode] = mapped_column(
        Enum(FailMode, name="fail_mode"), nullable=False
    )
    # Python attribute is metadata_ (Base.metadata is already taken); the
    # actual Postgres column is named metadata, matching forks.md.
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
