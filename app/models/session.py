import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db import Base

# strikes always carries all six category keys, even at 0, since Phase 3's
# escalation check reads any of them by name.
DEFAULT_STRIKES = {
    "pii": 0,
    "hallucination": 0,
    "toxicity": 0,
    "bias": 0,
    "prompt_injection": 0,
    "custom_policy": 0,
}


class Session(Base):
    __tablename__ = "session"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workload_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workload.workload_id"), nullable=False, index=True
    )
    cumulative_risk: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    strikes: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=lambda: dict(DEFAULT_STRIKES)
    )
    # Postgres holds the durable copy of the ledger; Redis (0.3) holds the
    # live one. Do not conflate the two stores (STATUS.md, Phase 4.1).
    ttl_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
