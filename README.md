# ControlPlane.ai

ControlPlane is an AI governance proxy. It sits between an application and its
model API (`AI Application → ControlPlane → Model API`), presenting an
OpenAI-compatible `/v1/chat/completions` endpoint so it drops in without any
change to how a caller already talks to a model.

Every request and response is evaluated against a six-category policy taxonomy
(`pii`, `hallucination`, `toxicity`, `bias`, `prompt_injection`, `custom_policy`)
across three evaluator tiers, and each session carries a risk ledger that
accumulates across turns, so ControlPlane catches a *pattern* of bad behavior,
not just a single bad message. See [How it works](#how-it-works) for the
mechanism.

The source lives at
[github.com/wowmimir/controlplane](https://github.com/wowmimir/controlplane).
Report bugs and suggest features in the
[issue tracker](https://github.com/wowmimir/controlplane/issues).


## Table of contents

- Requirements
- Recommended
- Installation
- Configuration
- Usage
- How it works
- The console
- Project structure
- Known limitations
- Troubleshooting
- FAQ


## Requirements

- Python 3.12+ with [uv](https://docs.astral.sh/uv/)
- Node.js 20.19+ and npm (for the console)
- A reachable PostgreSQL database
- A reachable Redis instance
- An OpenAI-compatible chat completions API (built and tested against a local
  Ollama instance)


## Recommended

- **[Ollama](https://ollama.com)**: a zero-cost local model server that speaks
  the OpenAI API shape, and what this project was developed against. Point at it
  with `MODEL_API_BASE_URL=http://localhost:11434/v1`.
- **Neon / Upstash**: managed Postgres and Redis. The connection strings in
  `.env.example` are written in their formats, but any Postgres/Redis host works.


## Installation

```bash
git clone https://github.com/wowmimir/controlplane.git
cd controlplane

uv sync                      # backend dependencies (this project uses uv)

cd console && npm install    # console dependencies
```


## Configuration

Copy the example env file and fill in real values:

```bash
cp .env.example .env
```

See `.env.example` for the full list with comments. In short:

| Variable | Required | What it's for |
|---|---|---|
| `DATABASE_URL` | Yes | Postgres, the durable audit trail (workloads, sessions, executions, findings) |
| `REDIS_URL` | Yes | Redis, the hot session risk ledger (15-minute TTL) |
| `MODEL_API_BASE_URL` | Yes | An OpenAI-compatible model API (built and tested against local Ollama) |
| `MODEL_API_KEY` | No | Only needed if your model API requires one |

The console has its own config: `console/.env.example` → `console/.env`, setting
`VITE_API_BASE_URL` (defaults to `http://localhost:8000` if the file is missing,
but setting it explicitly is recommended).


## Usage

Run the backend (Postgres, Redis, and the model API must all be reachable):

```bash
uv run uvicorn app.main:app --reload --port 8000
```

Run the console in a separate terminal:

```bash
cd console
npm run dev
```

The backend serves on `http://localhost:8000`, the console on
`http://localhost:5173`.

Populate the console with real traffic before you look at it:

```bash
uv run python scripts/seed_demo.py

# optional: register three differentiated demo workloads + shaped traffic
uv run python scripts/simulate_use_cases.py
```

### Calling the proxy

A clean request:

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "minimax-m3:cloud", "messages": [{"role": "user", "content": "What is the capital of France?"}]}'
```

A request that trips a cheap-tier PII block, returned before the model is ever
called:

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


## How it works

Each request and response runs through three evaluator tiers:

- **Cheap.** Synchronous regex/keyword checks (PII, prompt injection, toxicity,
  bias, secrets), gating release on both the request and the response side. What
  a match *does* depends on the workload's policy profile: `strict` blocks;
  `balanced` blocks too, except that for PII or secrets in a *response* it blanks
  the offending spans and releases the rest; `fast` flags for review and
  releases.
- **Medium.** A stubbed slot for embedding-similarity checks; wired but not
  implemented in this build.
- **Expensive.** An LLM-as-judge check, run asynchronously after the response has
  already been released (on every turn, or a ~10% sample for a `fast` workload),
  comparing the response against the request's context for unsupported or
  contradicted claims.

A per-session risk ledger accumulates across turns: `cumulative_risk` decays and
adds on every turn, per-category strikes expire on a rolling window, and a
session that crosses either threshold gets blocked on its *next* request
regardless of that request's own content (the thresholds themselves vary by
policy profile; `strict` trips sooner). This is what lets ControlPlane catch a
pattern of bad behavior, not just a single bad message. The exact math is locked
in `.agents/forks.md` (Fork #3). This README describes the shape, not the
constants, so the two can't drift out of sync.


## The console

Seven pages (plus a per-session drilldown), in `console/` (React + TypeScript +
Vite + Tailwind):

| Page | Shows |
|---|---|
| Dashboard | Aggregate request/block counts, findings by category, requests over time, governance-overhead p50/p95, and the false-positive rate across reviewed findings |
| Workloads | List, create, and edit workloads: policy profile (`strict` / `balanced` / `fast`), fail mode, latency/cost budgets, and per-category evaluator overrides |
| Sessions | Every session with its current ledger state; click a row for the drilldown: one session's risk / strikes / escalation and every execution and finding that fed it, the "why was this blocked" view |
| Review | Confirm or reject individual findings; feeds the Dashboard's false-positive rate |
| Detection Health | Per-pattern false-positive rate across all workloads, with a per-workload "suppress this pattern" toggle |
| Live Feed | The most recent executions across all sessions, polling every ~3 seconds |
| Playground | Type prompts straight through the proxy from the browser and see the reply, or the block reason and category; threads one session across turns |


## Project structure

```
app/         FastAPI backend: routers, evaluators, models, Redis/Postgres clients
console/     React + TypeScript + Tailwind frontend (Vite)
scripts/     seed_demo.py (a demo shot list) and simulate_use_cases.py (three
             differentiated workloads fed a labelled test corpus)
docs/        Human-facing docs (demo script, business-proposal outline, review reports)
.agents/     This build's own working state (specs, status, decisions); not
             required reading to use or run the app
```


## Known limitations

- **No streaming.** Only buffered (non-streaming) responses are supported;
  this was explicitly out of scope for this build.
- **Escalation-only blocks aren't visible in the console.** A block caused
  purely by accumulated session risk (rather than that turn's own content)
  writes no `Execution`/`Finding` row, since there's no per-turn evidence to
  attach, so it won't appear in the Dashboard, Session Drilldown, or Live
  Feed, even though it did block the request. Every other block type is
  fully visible.
- **`latency_budget_ms` and `cost_budget_per_request` are recorded per workload
  but not enforced.** Nothing in the evaluation path reads their values today.
  Every other `Workload` field does change behavior: `fail_mode` (fail open vs
  closed), and, as of Phase 8, `policy_profile` (escalation thresholds, the
  block / redact / flag action a violation triggers, and how often the async
  judge samples) and `metadata.category_overrides` (per-workload disable a
  category, raise a confidence floor, or mute a noisy pattern).
- **This is a hackathon-scope build.** There's no authentication on the
  `X-Workload-Id`/`X-Session-Id` headers (a caller can assert any session),
  nor on the console's write endpoints (`POST`/`PATCH /api/console/workloads`:
  anything that can reach the API port can create or edit a workload,
  including flipping its `fail_mode`); there's also no automated test suite.
  Every phase of this build was self-checked against a real, running instance
  instead.


## Troubleshooting

- **The console is empty.** It only shows data the proxy has already recorded.
  Run `uv run python scripts/seed_demo.py` to populate it.
- **The console can't reach the backend, or CORS errors in the browser.** The
  backend allows the `http://localhost:5173` origin only (`app/main.py`). Run the
  console on that port, or adjust the CORS config.
- **A dev `uvicorn` won't stop (Windows).** Kill it by port:
  ```powershell
  Get-NetTCPConnection -LocalPort 8000 -State Listen | Select -ExpandProperty OwningProcess | Stop-Process -Force
  ```


## FAQ

**Q: Is this production-ready?**

**A:** No. It's a hackathon-scope build: no authentication, no automated test
suite, no streaming. See [Known limitations](#known-limitations).

**Q: Can I point it at OpenAI or Anthropic instead of Ollama?**

**A:** Yes. Set `MODEL_API_BASE_URL` to any OpenAI-compatible endpoint and
`MODEL_API_KEY` if it needs one. No code change.

**Q: Where's the escalation math (thresholds, decay rate)?**

**A:** Locked in `.agents/forks.md` (Fork #3). This README describes the shape,
not the constants.
