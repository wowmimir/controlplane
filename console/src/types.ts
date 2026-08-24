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
}

// Mirrors app/schemas/console.py's WorkloadOut/WorkloadCreate/WorkloadUpdate.
export type PolicyProfile = 'strict' | 'balanced' | 'fast'
export type FailMode = 'fail_open' | 'fail_closed'

export interface WorkloadMetadata {
  name?: string
  geography?: string
  industry?: string
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

export interface FindingOut {
  finding_id: string
  category: string
  confidence: number
  evaluator_tier: string
  evidence_ref: { side?: string; pattern?: string; span?: [number, number] } | null
  timestamp: string
}

export interface ExecutionOut {
  execution_id: string
  tokens: number | null
  latency_ms: number | null
  retries: number
  tool_loop_count: number
  execution_risk_score: number | null
  blocked: boolean
  created_at: string
  findings: FindingOut[]
}

export interface SessionDetail extends SessionSummary {
  executions: ExecutionOut[]
}

// Mirrors app/schemas/console.py's FeedEntry.
export interface FeedEntry {
  execution_id: string
  session_id: string
  workload_id: string
  workload_name: string | null
  tokens: number | null
  latency_ms: number | null
  execution_risk_score: number | null
  blocked: boolean
  categories: string[]
  created_at: string
}
