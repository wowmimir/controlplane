"""ControlPlane.ai FastAPI app.

Run locally: uv run uvicorn app.main:app --reload --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import models  # noqa: F401  registers every model on Base.metadata
from app.db import Base, engine
from app.redis_client import redis_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await redis_client.ping()
    yield


app = FastAPI(title="ControlPlane.ai", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
