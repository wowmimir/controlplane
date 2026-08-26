# forks.md — ControlPlane.ai Locked Implementation Decisions

**Status:** Locked. These are resolved architectural forks — do not re-litigate.
**Rule:** If a task seems to require reopening one of these, STOP and ask the user. Do not silently override.

---

## Fork #1: Workload Model

**Decision:** Explicit `workload_id`, optional per-request, with graceful fallback.

- `Workload` is a first-class registered object. Relationship: **1 Workload → many Sessions → many Executions.**
- A Session cannot span two workloads.
- Every incoming request carries `workload_id` (optional). If omitted → resolves to a pre-registered `default` workload.
- **Default workload uses the `balanced` policy profile** (not a custom fourth profile).
- Workload carries:
  - `policy_profile`: `strict | balanced | fast`
  - `latency_budget_ms` (max governance overhead)
  - `cost_budget_per_request`
  - `fail_mode`: `fail_open | fail_closed` (see Fork #4)
  - category overrides (optional, per taxonomy category — post-MVP)
  - `metadata`: geography, industry tags (informational only, not a lookup dimension)
- Learn/Recommend loop is scoped **per-workload**, never merged across workloads.
- Console requires a workload management view (create/edit/list workloads and their profiles).

---

## Fork #2: Multi-Label Findings

**Decision:** Independent single-label evaluators (Option B). No monolithic multi-label classifier.

- Each evaluator is single-purpose and only knows its own category. A PII evaluator never needs to understand hallucination, and vice versa.
- One underlying problem (e.g., a fabricated PII detail) produces **multiple independent `Finding` records**, one per triggering evaluator/category — not one record with multiple labels.
- Correlation across findings (e.g., "these two findings came from the same sentence") is a **display/audit concern** via optional `evidence_ref`, not a scoring concern.
- `execution_risk_score` (feeds the session ledger) = **max confidence across all Findings in that execution**, regardless of how many evaluators fired.

### Locked Taxonomy

**Responsibility/Quality categories (feed the strike ledger):**
`pii`, `hallucination`, `toxicity`, `bias`, `prompt_injection`, `custom_policy`

**Operational signals (budget-only — do NOT touch strikes or the risk ledger):**
`tokens`, `latency`, `retries`, `tool_loop_count`

Do not conflate these two groups. Operational signals affect cost/latency budget enforcement only.

---

## Fork #3: Session State

**Decision:** Lightweight risk ledger (Option C) — not stateless, not full conversation replay.

- `session_id` is a first-class concept, distinct from `execution_id`.
- **Session boundary = whole task.** One session = one full conversation OR one complete agent invocation, start to final action. Do NOT split by tool-call sub-chains. (Future: hierarchical `parent_session_id` if ever needed — not now.)
- No `session_id` supplied → treated as a session of length 1 (graceful degradation, same pattern as workload fallback).
- Storage: **Redis**, keyed by `session_id`.

### Ledger Aggregation (exact math — do not approximate)

**Decaying cumulative risk (continuous):**
```
cumulative_risk = (cumulative_risk * 0.7) + execution_risk_score
```
- `decay_factor = 0.7`
- `execution_risk_score` = max confidence across all Findings in that execution (per Fork #2)

**Per-category strike counters (discrete):**
```
strikes: { pii: int, hallucination: int, toxicity: int, bias: int, prompt_injection: int, custom_policy: int }
```
- Increment a category's strike when a Finding in that category has `confidence > 0.7`.
- Strike window: only strikes from the **last 5 turns OR last 2 minutes** count. Older strikes expire out of the window.

**Escalation trigger (exact condition):**
```
escalate/block IF (cumulative_risk > 0.7) OR (any strikes[category] >= 3)
```

**TTL:** Session ledger expires after **15 minutes of inactivity**, then resets.

---

## Fork #4: Proxy Placement & Blocking Behavior

**Decision:** Inline reverse proxy, in both the request and response path.

Shape: `AI Application → ControlPlane (proxy) → Model API`, both legs.

### Request-side (prompt → model)
- **Cheap tier only.** Prompt injection heuristic, input PII scan.
- Runs synchronously, before the model API is even called (fails fast, saves the cost of a model call on a blocked request).
- **A request-side block counts as a strike**, same `Finding` schema, same category (`prompt_injection` or `pii`), same ledger mechanics as a response-side finding. Input and output are NOT treated differently.

### Response-side (model output → application)
- **Cheap tier always runs synchronously**, on every response, and gates release.
- Cheap tier's findings feed `execution_risk_score` → update the session ledger → check escalation trigger.
- **If the ledger already trips escalation after cheap tier → block/regenerate/route immediately.** Do not run medium/expensive tier.
- **If cheap tier is inconclusive** (not clearly safe, not clearly a violation) → run medium/expensive tier synchronously, but only **within the workload's `latency_budget_ms`.**
- **Expensive tier that would exceed the latency budget MUST run async, after the response is already released.** It cannot block or retroactively unsend the current response. It can only: (a) update the session ledger for future turns, (b) write to the audit trail, (c) trigger a post-hoc review/escalation action.

### Fail-open / Fail-closed
- This is a **workload-level policy setting** (part of the policy profile), not a global constant.
- If ControlPlane itself errors or times out: `fail_open` (let the response through) or `fail_closed` (block), per workload.

### Streaming
- **Out of scope for the Round 2 prototype.** Only buffered (non-streaming) responses are supported.
- State this as a known limitation if asked — do not silently attempt partial support.

---

## Fork #5: Round 2 Scope Boundary (Explicitly Deferred)

**Decision:** Streaming, real authentication/multi-tenancy/public deployment, real multi-provider routing, and a real (non-simulated) retrieval-verification pipeline are explicitly out of scope for the Round 2 build. Do not build these; do not re-litigate this without a direct instruction from the user.

**Rationale:** None of these are named anywhere in the Round 2 rubric's "Real-World Complexities" or "Solutioning Areas" lists, and the rubric explicitly permits "a limited or simulated scope" for the working prototype. Round 2 grading rewards demonstrating the core governance mechanism against the named complexities (varying risk tolerance per use case, the flag-vs-block tradeoff, overlapping categories, feedback loops, multi-turn compounding risk) — not production packaging. These four items remain legitimate future work and belong in the business proposal's phased roadmap as described-but-not-built, not in this build's milestone list (see `STATUS.md` Phase 8/9).

- **Streaming** was already out of scope per Fork #4; this reaffirms it specifically against the Round 2 rubric too, since it's the one item that would require reshaping the response-side interception design (Fork #4) rather than an additive change.
- **Auth/multi-tenancy/public deployment**: the existing caller-asserted-header gap (see `decisions.md`, 2026-08-23/24) stays accepted, unchanged, for this round.
- **Real multi-provider routing**: `app/model_client.py`'s single global `MODEL_API_BASE_URL` stays as-is. Phase 8.4's multi-use-case simulation gets its "varies by model" story for free by passing a different `model` field per demo workload against the same local Ollama instance, which already serves many distinct models — no routing work needed.
- **Real RAG/retrieval verification**: needs a document corpus, embeddings, and a vector store — several new subsystems, not a wire-up. If pursued at all, only as the explicitly-labeled "simulated" version in the optional Phase 9 (`STATUS.md`), never presented as production retrieval.

---

## Consolidated Data Model

```
Workload
  ├─ workload_id (PK)
  ├─ policy_profile: strict | balanced | fast
  ├─ latency_budget_ms
  ├─ cost_budget_per_request
  ├─ fail_mode: fail_open | fail_closed
  ├─ metadata: { geography, industry }
  │
  └─→ Session  (1 Workload : many Sessions)
        ├─ session_id (PK)
        ├─ workload_id (FK)
        ├─ cumulative_risk: float
        ├─ strikes: { pii, hallucination, toxicity, bias, prompt_injection, custom_policy }
        ├─ ttl_expires_at
        │
        └─→ Execution  (1 Session : many Executions)
              ├─ execution_id (PK)
              ├─ session_id (FK), workload_id (FK)
              ├─ operational: { tokens, latency_ms, retries, tool_loop_count }
              ├─ execution_risk_score: float
              │
              └─→ Finding  (many per Execution)
                    ├─ finding_id (PK)
                    ├─ execution_id (FK)
                    ├─ category: pii | hallucination | toxicity | bias | prompt_injection | custom_policy
                    ├─ confidence: float (0.0–1.0)
                    ├─ evaluator_tier: cheap | medium | expensive
                    ├─ evidence_ref: optional (span/offset)
                    ├─ timestamp
```

---

## Tech Stack (Locked)

| Layer | Choice |
|---|---|
| API/Proxy | Python (FastAPI), async-native |
| Session Ledger | Redis (Upstash), TTL 15min |
| Durable Store | PostgreSQL (Neon), FK chain per data model above |
| Async tasks (expensive-tier) | FastAPI `BackgroundTasks` (no Celery for MVP) |
| Frontend | React |
| API Shape | OpenAI-compatible (`/v1/chat/completions`) |
| Cheap evaluators | Regex/rule-based only — no ML dependency |
| Medium evaluators | Embedding similarity (sentence-transformer) |
| Expensive evaluators | LLM-as-judge via API call |

---

## What Is Explicitly NOT Locked (Fair Game to Decide During Build)

- Exact regex patterns / heuristic rules for cheap-tier evaluators
- Which embedding model for medium tier
- Which LLM/prompt for expensive-tier judge
- React component structure / exact console screens beyond "must have workload management view"
- Exact HTTP status codes and error body shapes (beyond: blocked = some 4xx)
- Database migration tooling
- Deployment target details

If a decision doesn't fit either the locked list above or this list, it's genuinely new — log it to `decisions.md` per AGENTS.md Rule 9, don't guess silently.