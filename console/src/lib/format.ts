// Shared id/name display helper. Extracted from Workloads.tsx (5.2) so
// Sessions.tsx/SessionDetail.tsx (5.3) use the same implementation instead
// of a second inline copy.
export function displayId(id: string, name?: string | null): string {
  if (name) return name
  return `${id.slice(0, 8)}…`
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
