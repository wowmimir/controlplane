# ControlPlane.ai

ControlPlane is an AI governance proxy. It sits between an application and its
model API (`AI Application → ControlPlane → Model API`), presenting an
OpenAI-compatible `/v1/chat/completions` endpoint so it drops in without any
change to how a caller already talks to a model.

Every request and response is evaluated against a six-category policy
taxonomy — `pii`, `hallucination`, `toxicity`, `bias`, `prompt_injection`,
`custom_policy` — across three evaluator tiers:

- **Cheap** — synchronous regex/keyword checks (PII, prompt injection,
  toxicity, bias, secrets), gating release on both the request and the
  response side. What a match *does* depends on the workload's policy
  profile: `strict` blocks; `balanced` blocks too, except that for PII or
  secrets in a *response* it blanks the offending spans and releases the
  rest; `fast` flags for review and releases.
- **Medium** — a stubbed slot for embedding-similarity checks; wired but not
  implemented in this build.
- **Expensive** — an LLM-as-judge check, run asynchronously after the
  response has already been released (on every turn, or a ~10% sample for a
  `fast` workload), comparing the response against the request's context for
  unsupported or contradicted claims.

A per-session risk ledger accumulates across turns: `cumulative_risk` decays
and adds on every turn, per-category strikes expire on a rolling window, and
a session that crosses either threshold gets blocked on its *next* request
regardless of that request's own content (the thresholds themselves vary by
policy profile — `strict` trips sooner). This is what lets ControlPlane
catch a pattern of bad behavior, not just a single bad message. The exact
math is locked in `.agents/forks.md` (Fork #3) — this README describes the
shape, not the constants, so the two can't drift out of sync.

## Quickstart

```bash
# 1. Install dependencies (this project uses uv)
uv sync

# 2. Configure environment
cp .env.example .env
# then fill in real values — see .env.example for what each variable is

# 3. Run the backend (Postgres + Redis + a model API must all be reachable)
uv run uvicorn app.main:app --reload --port 8000

# 4. Run the console (separate terminal)
cd console
cp .env.example .env
npm install
npm run dev

# 5. Populate the console with real traffic before you look at it
uv run python scripts/seed_demo.py

# 6. (optional) register three differentiated demo workloads + shaped traffic
uv run python scripts/simulate_use_cases.py
```

The backend serves on `http://localhost:8000`, the console on
`http://localhost:5173`.

## Configuration

See `.env.example` for the full list with comments. In short:

| Variable | Required | What it's for |
|---|---|---|
| `DATABASE_URL` | Yes | Postgres — the durable audit trail (workloads, sessions, executions, findings) |
| `REDIS_URL` | Yes | Redis — the hot session risk ledger (15-minute TTL) |
| `MODEL_API_BASE_URL` | Yes | An OpenAI-compatible model API (built and tested against local Ollama) |
| `MODEL_API_KEY` | No | Only needed if your model API requires one |

The console has its own config: `console/.env.example` → `console/.env`,
setting `VITE_API_BASE_URL` (defaults to `http://localhost:8000` if the file
is missing, but the quickstart above sets it explicitly).

## API example

A clean request:

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "minimax-m3:cloud", "messages": [{"role": "user", "content": "What is the capital of France?"}]}'
```

A request that trips a cheap-tier PII block, returned before the model is
ever called:

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "minimax-m3:cloud", "messages": [{"role": "user", "content": "Email the report to alice@example.com"}]}'
```

```json
{
  "error": {
    "message": "Request blocked by ControlPlane: pii detected in input.",
    "type": "controlplane_policy_violation",
    "param": null,
    "code": "pii"
  }
}
```

An optional `X-Workload-Id` header names a registered `Workload` whose policy
profile, fail mode, and per-category evaluator overrides govern the request
(falls back to a seeded `default` workload); an optional `X-Session-Id` header
threads a request into an existing session's risk ledger. Both are echoed back
as response headers, so a caller that omits `X-Session-Id` can still learn and
reuse the session ControlPlane generated for it.

## Console

Seven pages (plus a per-session drilldown), in `console/` (React + TypeScript + Vite + Tailwind):

| Page | Shows |
|---|---|
| Dashboard | Aggregate request/block counts, findings by category, requests over time, governance-overhead p50/p95, and the false-positive rate across reviewed findings |
| Workloads | List, create, and edit workloads — policy profile (`strict` / `balanced` / `fast`), fail mode, latency/cost budgets, and per-category evaluator overrides |
| Sessions | Every session with its current ledger state; click a row for the drilldown — one session's risk / strikes / escalation and every execution and finding that fed it, the "why was this blocked" view |
| Review | Confirm or reject individual findings; feeds the Dashboard's false-positive rate |
| Detection Health | Per-pattern false-positive rate across all workloads, with a per-workload "suppress this pattern" toggle |
| Live Feed | The most recent executions across all sessions, polling every ~3 seconds |
| Playground | Type prompts straight through the proxy from the browser and see the reply, or the block reason and category; threads one session across turns |

## Project structure

```
app/         FastAPI backend — routers, evaluators, models, Redis/Postgres clients
console/     React + TypeScript + Tailwind frontend (Vite)
scripts/     seed_demo.py (a demo shot list) and simulate_use_cases.py (three
             differentiated workloads fed a labelled test corpus)
docs/        Human-facing docs (demo script, business-proposal outline, review reports)
.agents/     This build's own working state (specs, status, decisions) — not
             required reading to use or run the app
```

## Known limitations

- **No streaming.** Only buffered (non-streaming) responses are supported;
  this was explicitly out of scope for this build.
- **Escalation-only blocks aren't visible in the console.** A block caused
  purely by accumulated session risk (rather than that turn's own content)
  writes no `Execution`/`Finding` row, since there's no per-turn evidence to
  attach — so it won't appear in the Dashboard, Session Drilldown, or Live
  Feed, even though it did block the request. Every other block type is
  fully visible.
- **`latency_budget_ms` and `cost_budget_per_request` are recorded per workload
  but not enforced.** Nothing in the evaluation path reads their values today.
  Every other `Workload` field does change behavior: `fail_mode` (fail open vs
  closed), and — as of Phase 8 — `policy_profile` (escalation thresholds, the
  block / redact / flag action a violation triggers, and how often the async
  judge samples) and `metadata.category_overrides` (per-workload disable a
  category, raise a confidence floor, or mute a noisy pattern).
- **This is a hackathon-scope build.** There's no authentication on the
  `X-Workload-Id`/`X-Session-Id` headers (a caller can assert any session),
  nor on the console's write endpoints (`POST`/`PATCH /api/console/workloads`
  — anything that can reach the API port can create or edit a workload,
  including flipping its `fail_mode`); there's also no automated test suite —
  every phase of this build was self-checked against a real, running instance
  instead.
