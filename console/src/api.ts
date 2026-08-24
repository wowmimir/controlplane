import type {
  DashboardSummary,
  FeedEntry,
  SessionDetail,
  SessionSummary,
  Workload,
  WorkloadCreate,
  WorkloadUpdate,
} from './types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL as string

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
