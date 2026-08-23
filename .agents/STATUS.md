# STATUS.md — ControlPlane.ai Build Progress

> Read this file FIRST in every session, per AGENTS.md Section 2.
> Then read `forks.md`, then `decisions.md`, before writing any code.

---

## Right Now

**Current Phase:** Phase 1 — The Proxy (Core Demo Path)
**Current Task:** 1.3 Request-Side Interception
**Next Action:** Write `.agents/prompts/1.3-request-side-interception-plan.md` per the Slim Workflow, then ask "Plan ready. Approve?"
**Blocked On:** Nothing.

---

## Session Handoff Notes
*(Agent: update this every session before ending, per AGENTS.md Rule 4 Step 7. User: read this first if resuming after a break.)*

- 2026-08-23: Shipped 0.1 Skeleton. `uv` initialized the project (`pyproject.toml`, `uv.lock`, git repo, no commits yet); `app/main.py` (an `app/` package, not a flat file, so later phases add routers/models without restructuring) exposes `GET /health` returning `{"status": "ok"}`. Self-checked with `curl` (200, correct body) and a clean `uvicorn` startup log. Tooling choices logged in `decisions.md`. Next session starts at 0.2 Database Models.
- 2026-08-23: Shipped 0.2 Database Models, per `prompts/0.2-database-models-plan.md` (now `Accepted`). Added `sqlalchemy`, `asyncpg`, `python-dotenv`. `app/db.py` holds the async engine/session/`Base`; `app/models/` has one file per entity (`workload.py`, `session.py`, `execution.py`, `finding.py`) plus `enums.py`, matching `forks.md`'s Consolidated Data Model exactly (UUID primary keys, native Postgres enums, `created_at` added to the three entities `forks.md` didn't already timestamp). `app/main.py`'s startup lifespan runs `Base.metadata.create_all` against Neon, no Alembic yet (logged as a Follow-up in the spec, revisit once the schema stabilizes). Also fixed two pre-existing repo issues found along the way: `.env` was not in `.gitignore` (now is), and it held `DB_URL` in a form `asyncpg` can't parse (`sslmode`/`channel_binding` aren't recognized; rewritten as `DATABASE_URL=postgresql+asyncpg://...?ssl=require`). Self-checked against the real Neon database: `create_all` created all four tables, a full Workload → Session → Execution → Finding round trip inserted and read back correctly, an invalid `category` value was rejected at the database level, and `/health` still returns 200 with the new startup lifespan wired in. Non-obvious implementation choices (the `metadata_` attribute workaround, the `str`+`Enum` pattern) logged in `decisions.md`. Next session starts at 0.3 Redis Client.
- 2026-08-23: Shipped 0.3 Redis Client, per `.agents/prompts/0.3-redis-client-plan.md` (`Accepted`). Added `redis` (redis-py, async interface). `app/redis_client.py` builds the client from `REDIS_URL` at module level (same pattern as `app/db.py`) and exposes `get_ledger`/`set_ledger`/`default_ledger`, storing the session ledger (`cumulative_risk`, all-six-category `strikes`) as one JSON blob per session with a 900s (15 min) TTL that resets on every write, per Fork #3. Scoped to storage plumbing only — the decay/strike-window/escalation math is still Phase 3's job, not built here. The `REDIS_URL` already in `.env` points at an Upstash database shared with another project, so every key is prefixed `controlplane:` (e.g. `controlplane:session:{id}:ledger`) to avoid collisions; this was flagged by the user mid-session and is not in `forks.md`. `app/main.py`'s lifespan now also `PING`s Redis at startup so a broken `REDIS_URL` fails fast, same fail-fast spirit as the DB's `create_all`. Self-checked against the real (shared) Upstash instance: default ledger shape returned for an unseen session, a set/get round trip matched exactly, TTL read ~899s immediately after write, and the actual key written carried the `controlplane:` prefix; app boot and `/health` (still 200) both verified with the new lifespan step. Client library choice and the key-prefix decision logged in `decisions.md`. Next session starts at 0.4 Default Workload Seed.
- 2026-08-23: Shipped 0.4 Default Workload Seed, per `.agents/prompts/0.4-default-workload-seed-plan.md` (`Accepted`), closing out Phase 0. `app/seed.py` defines `DEFAULT_WORKLOAD_ID`, a fixed sentinel UUID (`00000000-0000-0000-0000-000000000000`), and `seed_default_workload()`, an idempotent check-then-insert called from `app/main.py`'s lifespan (after `create_all`, before the Redis `ping()`). `forks.md`'s `Workload` schema has no name/slug field, so the default row is identified by this constant rather than by name — deliberately avoids reopening Fork #1's locked field list; Phase 1.2's fallback logic should import `DEFAULT_WORKLOAD_ID` from `app/seed.py` rather than re-deriving it. Seeded values: `policy_profile=balanced` (locked by Fork #1), `fail_mode=fail_open`, `latency_budget_ms=1000`, `cost_budget_per_request=0.10`, `metadata_=None` — the three unspecified values `STATUS.md` flagged, chosen and logged to `decisions.md` with rationale. Self-checked against the real Neon database: seeding twice leaves exactly one row at the sentinel id with no error, and every field matches the chosen values; full app boot (`create_all` → seed → Redis ping) and `/health` (200) verified together. Phase 0 (Foundation) is now complete. Next session starts at Phase 1's 1.1 OpenAI-Compatible Endpoint.
- 2026-08-23: Shipped 1.1 OpenAI-Compatible Endpoint, per `.agents/prompts/1.1-openai-compatible-endpoint-plan.md` (`Accepted`). `app/schemas/chat.py` defines the OpenAI-shaped `ChatCompletionRequest`/`ChatCompletionResponse` (plus `ChatMessage`, `Choice`, `Usage`); `app/routers/chat.py` adds `POST /v1/chat/completions`, registered in `app/main.py` via `app.include_router`. Settled the one open question `STATUS.md` flagged: `workload_id`/`session_id` are read from `X-Workload-Id`/`X-Session-Id` headers (optional, `uuid.UUID | None`), not body fields — keeps the JSON body byte-identical to OpenAI's schema per `AGENTS.md` Section 5's plug-and-play requirement; ratified with the user before building, logged to `decisions.md`. Scope deliberately stops at the endpoint shape: no DB/Redis resolution (that's 1.2), no evaluators (1.3), no real model call (1.4) — the handler returns an explicitly-labeled stub response (assistant message stating forwarding isn't implemented yet, `0` usage) rather than a fake reply that could be mistaken for real model output; also logged to `decisions.md`. Self-checked via `curl` against a running `uvicorn` instance: valid request with both headers → 200 + stub envelope; valid request with no headers → 200 (graceful degradation, foreshadowing 1.2's fallback); missing `messages` → 422; malformed `X-Workload-Id` → 422; `/health` still 200 (no regression). Next session starts at 1.2 Workload/Session Resolution.
- 2026-08-23: Shipped 1.2 Workload/Session Resolution, per `.agents/prompts/1.2-workload-session-resolution-plan.md` (`Accepted`). `app/routers/chat.py`'s `chat_completions` handler now resolves `X-Workload-Id`/`X-Session-Id` against real Postgres rows via `Depends(get_db)`: an absent workload header resolves to `DEFAULT_WORKLOAD_ID`; a present-but-unknown one returns `400` (ratified: fail fast rather than silently substitute the default, since that risked masking a caller misconfiguration behind the wrong policy profile/budgets). An absent session header creates a fresh `Session` row (a real length-1 session — a row must exist before any future `Execution` can FK to it); a present session id creates a row at that exact id if new, reuses it (refreshing `ttl_expires_at` to `now + 15min`, mirroring 0.3's Redis TTL-reset-on-write) if it already belongs to the resolved workload, or returns `400` if it belongs to a different one — enforcing Fork #1's "a Session cannot span two workloads" by rejecting the conflict outright rather than silently overriding either side. Also added, beyond `STATUS.md`'s literal wording but ratified with the user: every successful response now carries `X-Workload-Id`/`X-Session-Id` response headers reflecting the resolved values, so a caller who never supplies `session_id` can still learn and reuse the one ControlPlane generated — without this, no request could ever span more than one turn, which would make Phase 6.1's multi-turn escalation demo unreachable. All three decisions logged to `decisions.md`. Self-checked via `curl` against the real Neon database across all six resolution branches (default fallback, explicit valid workload, unknown workload → 400, new session created, existing session reused under the same workload, existing session rejected under a different *real* workload — the last one required inserting and then cleaning up a temporary second `Workload` row to test properly); `/health` still 200. Next session starts at 1.3 Request-Side Interception.

---

## Assumed Decisions Pending Ratification
*(Per AGENTS.md Rule 9 — decisions the agent made to avoid blocking, not yet explicitly confirmed by the user. Clear an entry once ratified, moving it to `decisions.md`.)*

- None yet.

---

## Build Milestones

Each item should map to one `prompts/[feature]-plan.md` spec, approved before code is written. Check off only after Self-Check passes (AGENTS.md Rule 4 Step 5) AND `decisions.md` is updated with any non-obvious choices made along the way.

### Phase 0 — Foundation
- [x] **0.1 Skeleton** — FastAPI app, `/health` endpoint returns 200.
- [x] **0.2 Database Models** — Connect to Postgres (Neon). SQLAlchemy models for `Workload`, `Session`, `Execution`, `Finding`, matching the schema in `forks.md` exactly (field names, FK chain, category enum).
- [x] **0.3 Redis Client** — Connect to Redis (Upstash). Ledger read/write helper with TTL support (15 min).
- [x] **0.4 Default Workload Seed** — On startup (or via seed script), ensure a `default` workload exists with `policy_profile=balanced`, sane default budgets, and `fail_mode` set explicitly (pick one, log to `decisions.md` — not specified in forks.md).

### Phase 1 — The Proxy (Core Demo Path)
- [x] **1.1 OpenAI-Compatible Endpoint** — `POST /v1/chat/completions`, accepts optional `workload_id` and `session_id` fields (outside strict OpenAI schema — confirm where these live: header vs body extension; log the choice to `decisions.md`).
- [x] **1.2 Workload/Session Resolution** — Resolve `workload_id` → fallback to `default`; resolve/create `session_id` → fallback to session-of-length-1 if absent.
- [ ] **1.3 Request-Side Interception** — Run cheap-tier checks (prompt injection, input PII) on the incoming prompt BEFORE calling the model API. On violation: write `Finding`, update ledger (per Fork #3 math), return blocked response — do not call the model.
- [ ] **1.4 Model Forwarding** — Forward the (unblocked) request to the real model API (OpenAI or Anthropic). Non-streaming only (Fork #4).
- [ ] **1.5 Response-Side Interception** — Intercept the model's response before returning it to the caller. Do not release yet.

### Phase 2 — Evaluators (The Brain)
- [ ] **2.1 Cheap: PII Regex** — Synchronous scanner for emails, phone numbers, SSN-shaped strings, etc. Target <5ms.
- [ ] **2.2 Cheap: Prompt Injection Heuristic** — Keyword/pattern-based jailbreak detection. Synchronous.
- [ ] **2.3 Cheap: Response-Side Reuse** — Confirm 2.1/2.2 detectors run on OUTPUT text too, not just input (they should be reusable, not input-only).
- [ ] **2.4 Medium: Embedding Similarity** — Grounding/hallucination heuristic. Only invoked when cheap tier is inconclusive (per Fork #4 decision tree).
- [ ] **2.5 Expensive: LLM-as-Judge** — Async evaluator, invoked when medium tier is inconclusive AND would exceed `latency_budget_ms` if run sync. Runs via `BackgroundTasks` after response release.
- [ ] **2.6 Toxicity/Bias/Custom Policy Evaluators** — Minimum viable version of each (even a stub heuristic) so the full 6-category taxonomy has *something* wired end-to-end for the demo, not just PII + hallucination.

### Phase 3 — Session Ledger & Control
- [ ] **3.1 Ledger Update Logic** — Implement exact math from `forks.md` Fork #3: `cumulative_risk = cumulative_risk * 0.7 + execution_risk_score`; per-category strikes with 5-turn/2-min window expiry.
- [ ] **3.2 Escalation Check** — `cumulative_risk > 0.7 OR any(strikes) >= 3` → trigger block/regenerate/route.
- [ ] **3.3 Fail-Open/Fail-Closed Handling** — Wrap the evaluation call path in error handling; on ControlPlane internal failure, honor the workload's `fail_mode`.
- [ ] **3.4 Response Release** — If not escalated: release response to caller. If escalated: return appropriate blocked/intervened response (status code + body shape — decide and log to `decisions.md`).

### Phase 4 — Audit Trail
- [ ] **4.1 Finding Persistence** — Every `Finding` (cheap, medium, expensive; request-side and response-side) written to Postgres, not just Redis. Redis = hot ledger, Postgres = durable record (per Fork #3/data model — do not conflate the two stores).
- [ ] **4.2 Execution Persistence** — Every `Execution` logged with operational signals (tokens, latency, retries, tool_loop_count) regardless of whether it was blocked.

### Phase 5 — Console UI ("Wow" Factor)
- [ ] **5.1 Dashboard** — Total requests, blocked count, findings by category, over time.
- [ ] **5.2 Workload Management View** — List/create/edit workloads and their policy profiles (required by Fork #1 — not optional).
- [ ] **5.3 Session Drilldown** — View a session's ledger state and the Findings that fed it (demonstrates the "why did this get blocked" story — the defensibility point from Fork #3's rationale).
- [ ] **5.4 Live Feed** — Real-time (polling or websocket) view of incoming executions and their verdicts, for the live demo.

### Phase 6 — Demo Polish
- [ ] **6.1 Seed/Simulation Script** — Scripted traffic that reliably triggers: a clean pass, a cheap-tier block, a ledger-driven multi-turn escalation, and an async expensive-tier finding — so the live demo doesn't depend on ad-libbing prompts.
- [ ] **6.2 README + Demo Video Script** — Per the competition deliverables (already noted as in progress separately).

---

## Known Blockers
- None currently.

---

## Notes for the Agent

- If a milestone above seems to require a decision not covered in `forks.md`, follow AGENTS.md Rule 9: propose the simplest reversible path, log it as an **Assumed Decision** in this file's section above, and keep moving — don't block waiting for approval unless it's genuinely load-bearing (e.g., changes the data model or contradicts a locked fork).
- Do not reorder phases. Phase 1 (the proxy) is the core demo mechanism — get a thin end-to-end slice (block on cheap-tier PII, nothing else) working before deepening any single phase.