import type {
  ChatResult,
  ChatTurn,
  DashboardSummary,
  DetectionHealthPattern,
  FeedEntry,
  FindingOut,
  ReviewQueueEntry,
  ReviewStatus,
  SessionDetail,
  SessionSummary,
  Workload,
  WorkloadCreate,
  WorkloadUpdate,
} from './types'

// 7.1/M5: falls back to the documented default rather than interpolating
// `undefined` into every request URL when console/.env is missing (e.g. a
// fresh clone that skipped `cp .env.example .env`). See
// docs/reviews/2026-08-25-phase6.md Major #5.
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000'

// Distinct from a generic Error so SessionDetail.tsx can render a
// "not found" state instead of the generic error state, per the 5.3 spec.
export class NotFoundError extends Error {}

async function parseOrThrow<T>(response: Response): Promise<T> {
  if (!response.ok) {
    if (response.status === 404) {
      throw new NotFoundError('Not found')
    }
    const body = await response.json().catch(() => null)
    const detail =
      body && typeof body === 'object' && 'detail' in body ? JSON.stringify(body.detail) : null
    throw new Error(detail ?? `ControlPlane API returned ${response.status}`)
  }
  return (await response.json()) as T
}

export async function fetchSummary(): Promise<DashboardSummary> {
  const response = await fetch(`${API_BASE_URL}/api/console/summary`)
  return parseOrThrow<DashboardSummary>(response)
}

export async function fetchWorkloads(): Promise<Workload[]> {
  const response = await fetch(`${API_BASE_URL}/api/console/workloads`)
  return parseOrThrow<Workload[]>(response)
}

export async function createWorkload(payload: WorkloadCreate): Promise<Workload> {
  const response = await fetch(`${API_BASE_URL}/api/console/workloads`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return parseOrThrow<Workload>(response)
}

export async function updateWorkload(
  workloadId: string,
  payload: WorkloadUpdate,
): Promise<Workload> {
  const response = await fetch(`${API_BASE_URL}/api/console/workloads/${workloadId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return parseOrThrow<Workload>(response)
}

export async function fetchSessions(): Promise<SessionSummary[]> {
  const response = await fetch(`${API_BASE_URL}/api/console/sessions`)
  return parseOrThrow<SessionSummary[]>(response)
}

export async function fetchSessionDetail(sessionId: string): Promise<SessionDetail> {
  const response = await fetch(`${API_BASE_URL}/api/console/sessions/${sessionId}`)
  return parseOrThrow<SessionDetail>(response)
}

export async function fetchFeed(): Promise<FeedEntry[]> {
  const response = await fetch(`${API_BASE_URL}/api/console/feed`)
  return parseOrThrow<FeedEntry[]>(response)
}

// 8.3: record an operator's judgment on a finding. Returns the updated finding.
export async function patchFindingReview(
  findingId: string,
  reviewStatus: ReviewStatus,
): Promise<FindingOut> {
  const response = await fetch(`${API_BASE_URL}/api/console/findings/${findingId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ review_status: reviewStatus }),
  })
  return parseOrThrow<FindingOut>(response)
}

// 8.3: the review queue. Omit reviewStatus for all findings; pass it to filter.
export async function fetchFindings(params?: {
  reviewStatus?: ReviewStatus
  limit?: number
}): Promise<ReviewQueueEntry[]> {
  const query = new URLSearchParams()
  if (params?.reviewStatus) query.set('review_status', params.reviewStatus)
  if (params?.limit != null) query.set('limit', String(params.limit))
  const suffix = query.toString() ? `?${query.toString()}` : ''
  const response = await fetch(`${API_BASE_URL}/api/console/findings${suffix}`)
  return parseOrThrow<ReviewQueueEntry[]>(response)
}

// 8.3: per-pattern false-positive rates + which workloads suppress each.
export async function fetchDetectionHealth(): Promise<DetectionHealthPattern[]> {
  const response = await fetch(`${API_BASE_URL}/api/console/detection-health`)
  return parseOrThrow<DetectionHealthPattern[]>(response)
}

// 10.1: the playground's one call - POST to the OpenAI-shaped proxy entry
// point, not /api/console/*. Deliberately does NOT use parseOrThrow: the page
// needs the 4xx/5xx body (the block reason, the category) as much as the 200
// body, so every outcome comes back as a classified ChatResult, never a throw.
// See .agents/prompts/10.1-prompt-playground-page-plan.md.
export async function sendChatCompletion(params: {
  model: string
  messages: ChatTurn[]
  workloadId?: string | null
  sessionId?: string | null
}): Promise<ChatResult> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (params.workloadId) headers['X-Workload-Id'] = params.workloadId
  if (params.sessionId) headers['X-Session-Id'] = params.sessionId

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/v1/chat/completions`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ model: params.model, messages: params.messages }),
    })
  } catch {
    return { kind: 'error', message: 'Could not reach ControlPlane.', sessionId: null }
  }

  // Requires app/main.py's CORS expose_headers (10.1) - null otherwise.
  const sessionId = response.headers.get('X-Session-Id')
  const body: unknown = await response.json().catch(() => null)
  const record = (body ?? {}) as Record<string, unknown>

  if (response.ok) {
    const choices = record.choices as { message?: { content?: string } }[] | undefined
    return { kind: 'ok', content: choices?.[0]?.message?.content ?? '', sessionId }
  }

  const err = (record.error ?? {}) as { message?: string; type?: string; code?: string }
  // The proxy's own blocks use the OpenAI-shaped { error: {...} } envelope;
  // FastAPI HTTPException paths (unknown workload, cross-workload session id -
  // app/routers/chat.py) return { detail: "..." } instead. Fall back to that
  // so a workload-mismatch 400 explains itself rather than showing a bare code.
  const message =
    err.message ??
    (typeof record.detail === 'string' ? record.detail : null) ??
    `ControlPlane returned ${response.status}.`
  if (response.status === 403 && err.type === 'controlplane_session_escalated') {
    return { kind: 'escalated', message, sessionId }
  }
  if (response.status === 403) {
    return { kind: 'blocked', message, code: err.code ?? 'policy_violation', sessionId }
  }
  return { kind: 'error', message, sessionId }
}
