import type { CategoryOverride } from '../types'

// Shared id/name display helper. Extracted from Workloads.tsx (5.2) so
// Sessions.tsx/SessionDetail.tsx (5.3) use the same implementation instead
// of a second inline copy.
export function displayId(id: string, name?: string | null): string {
  if (name) return name
  return `${id.slice(0, 8)}…`
}

// 8.6: a short one-line summary of a workload's category_overrides for the
// Workloads table's read-only "Overrides" column. Empty string when the
// workload has none. See
// .agents/prompts/8.6-per-workload-category-overrides-plan.md.
export function formatCategoryOverrides(
  metadata: { category_overrides?: Record<string, CategoryOverride> } | null,
): string {
  const overrides = metadata?.category_overrides
  if (!overrides || typeof overrides !== 'object') return ''
  const parts: string[] = []
  for (const [category, rule] of Object.entries(overrides)) {
    if (!rule || typeof rule !== 'object') continue
    if (rule.enabled === false) {
      parts.push(`${category} off`)
      continue
    }
    if (typeof rule.confidence_floor === 'number' && rule.confidence_floor > 0) {
      parts.push(`${category} ≥${rule.confidence_floor}`)
    }
    for (const pattern of rule.disabled_patterns ?? []) {
      parts.push(`${category} −${pattern}`)
    }
  }
  return parts.join(' · ')
}

// 7.1/M3: ttl_expires_at is always refreshed to now + 15min on every request
// that touches a session's ledger, so it doubles as "is the live Redis
// ledger still around". The Postgres-sourced escalated/cumulative_risk/
// strikes on SessionSummary/SessionDetail never expire, so a session that
// escalated and then went quiet keeps showing as escalated forever unless
// the UI checks this separately - see docs/reviews/2026-08-25-phase6.md
// Major #3. Shared here (not duplicated) since Sessions.tsx and
// SessionDetail.tsx both need it.
export function isLedgerLive(ttlExpiresAt: string): boolean {
  return new Date(ttlExpiresAt).getTime() > Date.now()
}
