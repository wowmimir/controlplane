import { useCallback, useEffect, useState } from 'react'
import { fetchSummary } from './api'
import { CategoryChart } from './components/CategoryChart'
import { OverTimeChart } from './components/OverTimeChart'
import { StatTile } from './components/StatTile'
import type { DashboardSummary } from './types'

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: DashboardSummary; fetchedAt: Date }

export function Dashboard() {
  const [state, setState] = useState<LoadState>({ status: 'loading' })

  const load = useCallback(() => {
    setState({ status: 'loading' })
    fetchSummary()
      .then((data) => setState({ status: 'ready', data, fetchedAt: new Date() }))
      .catch((error: unknown) =>
        setState({
          status: 'error',
          message: error instanceof Error ? error.message : 'Something went wrong.',
        }),
      )
  }, [])

  useEffect(() => {
    load()
  }, [load])

  return (
    <>
      <div className="border-b border-[var(--color-border)]">
        <div className="mx-auto flex max-w-6xl flex-wrap items-baseline justify-between gap-2 px-6 py-5">
          <h1 className="text-xl font-medium text-[var(--color-ink)]">Dashboard</h1>
          <div className="flex items-center gap-3">
            {state.status === 'ready' ? (
              <span className="text-xs text-[var(--color-muted)]">
                Updated {state.fetchedAt.toLocaleTimeString()}
              </span>
            ) : null}
            <button
              type="button"
              onClick={load}
              disabled={state.status === 'loading'}
              className="rounded-sm border border-[var(--color-border)] px-3 py-1.5 text-sm text-[var(--color-body)] transition-colors duration-[var(--duration-base)] hover:border-[var(--color-accent)] hover:text-[var(--color-ink)] disabled:opacity-50"
            >
              {state.status === 'loading' ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>
        </div>
      </div>

      <main className="mx-auto max-w-6xl px-6 py-8">
        {state.status === 'loading' && (
          <div role="status" className="py-24 text-center text-sm text-[var(--color-muted)]">
            Loading dashboard data…
          </div>
        )}

        {state.status === 'error' && (
          <div
            role="alert"
            className="rounded-md border border-[var(--color-error)]/40 bg-[var(--color-surface)] p-6 text-center"
          >
            <p className="font-medium text-[var(--color-error)]">Couldn't load dashboard data</p>
            <p className="mt-1 text-sm text-[var(--color-muted)]">{state.message}</p>
            <button
              type="button"
              onClick={load}
              className="mt-4 rounded-sm border border-[var(--color-border)] px-3 py-1.5 text-sm text-[var(--color-body)] hover:border-[var(--color-accent)] hover:text-[var(--color-ink)]"
            >
              Try again
            </button>
          </div>
        )}

        {state.status === 'ready' && (
          <div className="flex flex-col gap-6">
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
              <StatTile label="Total requests" value={state.data.total_requests} />
              <StatTile
                label="Blocked"
                value={state.data.blocked_count}
                accent
                caveat="Escalation-only blocks (a session already in cooldown, no new content scanned) aren't included - Redis doesn't retain history for those past 15 minutes."
              />
              <StatTile
                label="Governance overhead"
                value={
                  state.data.governance_overhead_p50_ms != null &&
                  state.data.governance_overhead_p95_ms != null
                    ? `${Math.round(state.data.governance_overhead_p50_ms)} / ${Math.round(
                        state.data.governance_overhead_p95_ms,
                      )} ms`
                    : '— / — ms'
                }
                caveat="p50 / p95 of the synchronous interception path (cheap-tier scan + ledger read/write). The async judge runs after the response is released and isn't counted."
              />
              <StatTile
                label="False-positive rate"
                value={
                  state.data.false_positive_rate != null
                    ? `${Math.round(state.data.false_positive_rate * 100)}%`
                    : '—'
                }
                caveat={
                  state.data.reviewed_findings > 0
                    ? `Of reviewed findings only. ${state.data.false_positive_findings} of ${state.data.reviewed_findings} reviewed findings were marked a false positive; the unreviewed backlog is not in the denominator.`
                    : 'Of reviewed findings only. Nothing has been reviewed yet. Confirm or reject findings on a session or the Review page and this starts to fill in.'
                }
              />
            </div>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              <CategoryChart data={state.data.findings_by_category} />
              <OverTimeChart data={state.data.over_time} />
            </div>
          </div>
        )}
      </main>
    </>
  )
}
