import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchSessions } from './api'
import { displayId, isLedgerLive } from './lib/format'
import type { SessionSummary } from './types'

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: SessionSummary[] }

// ttl_expires_at is always refreshed to now + 15min on every request that
// touches a session's ledger (decisions.md, 2026-08-23), so subtracting 15
// minutes back out recovers the session's actual last-activity time - not
// an invented value, a derivation from that documented invariant.
const LEDGER_TTL_MS = 15 * 60 * 1000

function lastActivity(session: SessionSummary): Date {
  return new Date(new Date(session.ttl_expires_at).getTime() - LEDGER_TTL_MS)
}

function strikesSummary(strikes: Record<string, number>): string {
  const active = Object.entries(strikes).filter(([, count]) => count > 0)
  if (active.length === 0) return '—'
  return active.map(([category, count]) => `${category} ×${count}`).join(', ')
}

function EscalatedPill({ escalated, ledgerLive }: { escalated: boolean; ledgerLive: boolean }) {
  if (!escalated) return <span className="text-[var(--color-muted)]">—</span>
  if (!ledgerLive) {
    // 7.1/M3: the ledger that actually gates traffic expired 15 minutes
    // after last activity; the Postgres cumulative_risk/strikes mirror
    // never expires, so without this distinction the pill keeps claiming
    // an active state that stopped being true.
    return (
      <span
        title="This session's live Redis ledger has expired; a new turn today would start fresh."
        className="inline-block rounded-full border border-[var(--color-border)] px-2.5 py-0.5 text-xs font-medium text-[var(--color-muted)]"
      >
        Escalated (expired)
      </span>
    )
  }
  return (
    <span className="inline-block rounded-full border border-[var(--color-error)]/40 px-2.5 py-0.5 text-xs font-medium text-[var(--color-error)]">
      Escalated
    </span>
  )
}

export function Sessions() {
  const navigate = useNavigate()
  const [state, setState] = useState<LoadState>({ status: 'loading' })
  const [jumpId, setJumpId] = useState('')

  const load = useCallback(() => {
    setState({ status: 'loading' })
    fetchSessions()
      .then((data) => setState({ status: 'ready', data }))
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

  function handleJump(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const trimmed = jumpId.trim()
    if (!trimmed) return
    navigate(`/sessions/${trimmed}`)
  }

  return (
    <>
      <div className="border-b border-[var(--color-border)]">
        <div className="mx-auto flex max-w-6xl flex-wrap items-start justify-between gap-4 px-6 py-5">
          <div>
            <h1 className="text-xl font-medium text-[var(--color-ink)]">Sessions</h1>
            <p className="mt-1 max-w-prose text-sm text-[var(--color-muted)]">
              The 50 most recent sessions, newest first. Open one to see its ledger state and the
              findings that fed it.
            </p>
          </div>
          <form onSubmit={handleJump} className="flex shrink-0 items-center gap-2">
            <label htmlFor="jump-to-session" className="sr-only">
              Jump to a session by id
            </label>
            <input
              id="jump-to-session"
              type="text"
              value={jumpId}
              onChange={(event) => setJumpId(event.target.value)}
              placeholder="Paste a session id…"
              className="w-56 rounded-sm border border-[var(--color-border)] bg-[var(--color-canvas)] px-3 py-1.5 text-sm text-[var(--color-ink)] outline-none focus-visible:border-[var(--color-accent)] focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]/40"
            />
            <button
              type="submit"
              className="rounded-sm border border-[var(--color-border)] px-3 py-1.5 text-sm text-[var(--color-body)] transition-colors duration-[var(--duration-base)] hover:border-[var(--color-accent)] hover:text-[var(--color-ink)]"
            >
              Go
            </button>
          </form>
        </div>
      </div>

      <main className="mx-auto max-w-6xl px-6 py-8">
        {state.status === 'loading' && (
          <div role="status" className="py-24 text-center text-sm text-[var(--color-muted)]">
            Loading sessions…
          </div>
        )}

        {state.status === 'error' && (
          <div
            role="alert"
            className="rounded-md border border-[var(--color-error)]/40 bg-[var(--color-surface)] p-6 text-center"
          >
            <p className="font-medium text-[var(--color-error)]">Couldn't load sessions</p>
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

        {state.status === 'ready' && state.data.length === 0 && (
          <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] p-12 text-center">
            <p className="text-[var(--color-ink)]">No sessions yet</p>
            <p className="mt-1 text-sm text-[var(--color-muted)]">
              Sessions appear here once a caller sends a request through the proxy.
            </p>
          </div>
        )}

        {state.status === 'ready' && state.data.length > 0 && (
          <div className="overflow-x-auto rounded-md border border-[var(--color-border)] bg-[var(--color-surface)]">
            <table className="w-full min-w-[900px] border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-xs text-[var(--color-muted)]">
                  <th scope="col" className="px-4 py-3 font-medium">
                    Session
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Workload
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Status
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Cumulative risk
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Strikes
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Executions
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Last activity
                  </th>
                </tr>
              </thead>
              <tbody>
                {state.data.map((session) => (
                  <tr
                    key={session.session_id}
                    className="cursor-pointer border-b border-[var(--color-border)] transition-colors duration-[var(--duration-base)] last:border-0 hover:bg-[var(--color-canvas)]"
                    onClick={() => navigate(`/sessions/${session.session_id}`)}
                  >
                    <td className="px-4 py-3">
                      <a
                        href={`/sessions/${session.session_id}`}
                        onClick={(event) => {
                          event.preventDefault()
                          navigate(`/sessions/${session.session_id}`)
                        }}
                        title={session.session_id}
                        className="text-[var(--color-accent)] underline-offset-2 hover:underline"
                      >
                        {displayId(session.session_id)}
                      </a>
                    </td>
                    <td className="px-4 py-3 text-[var(--color-body)]" title={session.workload_id}>
                      {displayId(session.workload_id, session.workload_name)}
                    </td>
                    <td className="px-4 py-3">
                      <EscalatedPill
                        escalated={session.escalated}
                        ledgerLive={isLedgerLive(session.ttl_expires_at)}
                      />
                    </td>
                    <td className="px-4 py-3 tabular-nums text-[var(--color-body)]">
                      {session.cumulative_risk.toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-[var(--color-body)]">
                      {strikesSummary(session.strikes)}
                    </td>
                    <td className="px-4 py-3 tabular-nums text-[var(--color-body)]">
                      {session.execution_count}
                    </td>
                    <td className="px-4 py-3 text-[var(--color-muted)]">
                      {lastActivity(session).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </>
  )
}
