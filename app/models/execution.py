import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db import Base
from app.models.enums import Disposition


class Execution(Base):
    __tablename__ = "execution"

    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("session.session_id"), nullable=False, index=True
    )
    # Denormalized from session.workload_id (forks.md's own field list has
    # it), so a workload level query never needs a join through Session.
    workload_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workload.workload_id"), nullable=False, index=True
    )
    tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_loop_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    execution_risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 8.2: what ControlPlane decided about this turn - clean/flagged/blocked.
    # Every write site sets this explicitly; the default only covers a
    # genuinely-clean row no branch above happens to touch. See
    # .agents/prompts/8.2-tiered-decision-logic-plan.md.
    disposition: Mapped[Disposition] = mapped_column(
        Enum(Disposition, name="disposition"), nullable=False, default=Disposition.clean
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
