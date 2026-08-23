import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db import Base
from app.models.enums import EvaluatorTier, FindingCategory


class Finding(Base):
    __tablename__ = "finding"

    finding_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("execution.execution_id"), nullable=False, index=True
    )
    category: Mapped[FindingCategory] = mapped_column(
        Enum(FindingCategory, name="finding_category"), nullable=False
    )
    # Meant to hold 0.0 to 1.0; checked at the application layer for this
    # milestone, not a database constraint (forks.md does not ask for one).
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evaluator_tier: Mapped[EvaluatorTier] = mapped_column(
        Enum(EvaluatorTier, name="evaluator_tier"), nullable=False
    )
    evidence_ref: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
