import type {
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
