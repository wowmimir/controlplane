"""Seeds the default Workload row Phase 1.2 falls back to when a request
omits workload_id (forks.md Fork #1). forks.md's Workload schema has no
name/slug field, so the default row is identified by a fixed sentinel UUID
rather than by name; see .agents/prompts/0.4-default-workload-seed-plan.md.
"""

import uuid

from sqlalchemy import select

from app.db import async_session
from app.models.enums import FailMode, PolicyProfile
from app.models.workload import Workload

DEFAULT_WORKLOAD_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")


async def seed_default_workload() -> None:
    async with async_session() as session:
        existing = await session.scalar(
            select(Workload).where(Workload.workload_id == DEFAULT_WORKLOAD_ID)
        )
        if existing is not None:
            return

        session.add(
            Workload(
                workload_id=DEFAULT_WORKLOAD_ID,
                policy_profile=PolicyProfile.balanced,
                latency_budget_ms=1000,
                cost_budget_per_request=0.10,
                fail_mode=FailMode.fail_open,
                metadata_=None,
            )
        )
        await session.commit()
