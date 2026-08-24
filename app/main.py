"""ControlPlane.ai FastAPI app.

Run locally: uv run uvicorn app.main:app --reload --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401  registers every model on Base.metadata
from app.db import Base, engine
from app.redis_client import redis_client
from app.routers.chat import router as chat_router
from app.routers.console import router as console_router
from app.seed import seed_default_workload


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed_default_workload()
    await redis_client.ping()
    yield


app = FastAPI(title="ControlPlane.ai", lifespan=lifespan)

# Console (5.1+) is a separate Vite dev server (default origin below) calling
# this API directly from the browser - per .agents/prompts/5.1-dashboard-plan.md.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(console_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
