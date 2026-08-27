// Mirrors app/schemas/console.py's DashboardSummary exactly.
export interface CategoryCount {
  category: string
  count: number
}

export interface TimeBucket {
  bucket: string
  total: number
  blocked: number
}

export interface DashboardSummary {
  total_requests: number
  blocked_count: number
  findings_by_category: CategoryCount[]
  over_time: TimeBucket[]
  // 8.4: p50/p95 of measured sync governance overhead (ms), or null on a
  // fresh DB with no full-pipeline turns yet.
  governance_overhead_p50_ms: number | null
  governance_overhead_p95_ms: number | null
  // 8.3: the trust metric. reviewed_findings = confirmed + false_positive
  // (unreviewed excluded); false_positive_rate is over that denominator, or
  // null when nothing has been reviewed.
  reviewed_findings: number
  false_positive_findings: number
  false_positive_rate: number | null
}

// Mirrors app/schemas/console.py's WorkloadOut/WorkloadCreate/WorkloadUpdate.
export type PolicyProfile = 'strict' | 'balanced' | 'fast'
export type FailMode = 'fail_open' | 'fail_closed'

// 8.6: per-category cheap-tier tuning, stored inside the free-form metadata
// JSONB (no schema change). Set via the API / scripts/simulate_use_cases.py;
// shown read-only in the Workloads table. See
// .agents/prompts/8.6-per-workload-category-overrides-plan.md.
export interface CategoryOverride {
  enabled?: boolean
  confidence_floor?: number
  disabled_patterns?: string[]
}

export interface WorkloadMetadata {
  name?: string
  geography?: string
  industry?: string
  category_overrides?: Record<string, CategoryOverride>
  [key: string]: unknown
}

export interface Workload {
  workload_id: string
  policy_profile: PolicyProfile
  fail_mode: FailMode
  latency_budget_ms: number
  cost_budget_per_request: number | null
  metadata: WorkloadMetadata | null
  created_at: string
}

export interface WorkloadCreate {
  policy_profile: PolicyProfile
  fail_mode: FailMode
  latency_budget_ms: number
  cost_budget_per_request: number | null
  metadata: WorkloadMetadata | null
}

export type WorkloadUpdate = Partial<WorkloadCreate>

// Mirrors app/schemas/console.py's SessionSummary/FindingOut/ExecutionOut/SessionDetail.
export interface SessionSummary {
  session_id: string
  workload_id: string
  workload_name: string | null
  cumulative_risk: number
  strikes: Record<string, number>
  escalated: boolean
  execution_count: number
  ttl_expires_at: string
  created_at: string
}

// 8.3: an operator's judgment on a finding.
export type ReviewStatus = 'unreviewed' | 'confirmed' | 'false_positive'

export interface FindingOut {
  finding_id: string
  category: string
  confidence: number
  evaluator_tier: string
  // 8.5: masked_excerpt is the matched span blanked to [REDACTED:<category>]
  // with ~40 chars of real context each side - present on any cheap-tier
  // finding that carries a span. Never contains the raw match.
  evidence_ref: {
    side?: string
    pattern?: string
    span?: [number, number]
    masked_excerpt?: string
  } | null
  timestamp: string
  // 8.3: unreviewed / confirmed / false_positive.
  review_status: ReviewStatus
}

// 8.3: one row of GET /api/console/findings - a finding plus enough context
// to review it without opening its session.
export interface ReviewQueueEntry {
  finding_id: string
  category: string
  confidence: number
  evaluator_tier: string
  pattern: string | null
  side: string | null
  masked_excerpt: string | null
  review_status: ReviewStatus
  execution_id: string
  disposition: Disposition
  session_id: string
  workload_id: string
  workload_name: string | null
  timestamp: string
}

// 8.3: one detection pattern's review outcomes, aggregated across every
// workload, from GET /api/console/detection-health.
export interface DetectionHealthPattern {
  pattern: string
  category: string
  confirmed: number
  false_positive: number
  unreviewed: number
  reviewed: number
  false_positive_rate: number | null
  needs_attention: boolean
  suppressed_by: string[]
}

// 8.2: clean/flagged/blocked - a fast-profile cheap-tier hit releases as
// 200 with disposition=flagged instead of blocking (strict/balanced keep
// hard-blocking). Replaces the old derived `blocked: boolean`.
// 8.5: `redacted` - a balanced-profile response-side pii/custom_policy hit
// where the matched span(s) were blanked and the edited response released.
export type Disposition = 'clean' | 'flagged' | 'blocked' | 'redacted'

export interface ExecutionOut {
  execution_id: string
  tokens: number | null
  latency_ms: number | null
  retries: number
  tool_loop_count: number
  execution_risk_score: number | null
  disposition: Disposition
  // 8.4: the model this turn's request named, and the measured sync
  // governance overhead in ms (null on a request-side block row / pre-8.4).
  model: string | null
  governance_overhead_ms: number | null
  created_at: string
  findings: FindingOut[]
}

export interface SessionDetail extends SessionSummary {
  executions: ExecutionOut[]
}

// 10.1: the prompt playground talks to POST /v1/chat/completions directly
// (the OpenAI-shaped proxy entry point), not the /api/console/* surface the
// types above mirror. See .agents/prompts/10.1-prompt-playground-page-plan.md.
export interface ChatTurn {
  role: 'user' | 'assistant'
  content: string
  // 10.1 review M2: a turn the proxy rejected (blocked / escalation-blocked).
  // Shown in the transcript but NOT resent on the next turn - the proxy never
  // produced a reply for it, and forwarding a blocked prompt to the model on a
  // later turn contradicts the "blocked before the model is called" story.
  blocked?: boolean
}

// The outcome of one /v1/chat/completions call, already classified by HTTP
// status + error.type so the page never re-inspects the raw response.
// - ok:        200, a model reply (clean / flagged / redacted all look the same
//              here by design - a flagged release carries no body signal, a
//              redacted one shows its [REDACTED:x] text inline).
// - blocked:   403, controlplane_policy_violation - this turn's content.
// - escalated: 403, controlplane_session_escalated - the session's accrued risk.
// - error:     502/503/network - ControlPlane or the upstream model failed.
export type ChatResult =
  | { kind: 'ok'; content: string; sessionId: string | null }
  | { kind: 'blocked'; message: string; code: string; sessionId: string | null }
  | { kind: 'escalated'; message: string; sessionId: string | null }
  // sessionId is carried here too: a 502 / fail-closed 503 still sets the
  // X-Session-Id header and has already created a real Session row, so a
  // first-turn upstream failure should not orphan that session (10.1 review).
  | { kind: 'error'; message: string; sessionId: string | null }

// The confirmed-working Ollama tag (decisions.md, 2026-08-23). Editable in the
// playground; a Workload row stores no model of its own.
export const DEFAULT_PLAYGROUND_MODEL = 'minimax-m3:cloud'

// Mirrors app/schemas/console.py's FeedEntry.
export interface FeedEntry {
  execution_id: string
  session_id: string
  workload_id: string
  workload_name: string | null
  tokens: number | null
  latency_ms: number | null
  execution_risk_score: number | null
  disposition: Disposition
  model: string | null
  categories: string[]
  created_at: string
}
