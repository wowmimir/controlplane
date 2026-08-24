import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchFeed } from './api'
import { displayId } from './lib/format'
import type { FeedEntry } from './types'

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: FeedEntry[] }

// Polling, not a push transport - ratified in .agents/prompts/5.4-live-feed-plan.md
// (a websocket/SSE push would need new shared state threaded through
// app/routers/chat.py's hardened Execution-commit sites; a 3s poll reads as
// "live" to a human demo audience at this project's actual traffic volume).
const POLL_INTERVAL_MS = 3000
// How long a freshly-arrived row keeps its "just arrived" accent highlight.
const NEW_ROW_HIGHLIGHT_MS = 1000

function BlockedBadge({ blocked }: { blocked: boolean }) {
  return (
    <span
      className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-medium ${
        blocked
          ? 'border-[var(--color-error)]/40 text-[var(--color-error)]'
          : 'border-[var(--color-success)]/40 text-[var(--color-success)]'
      }`}
    >
      {blocked ? 'Blocked' : 'Clean'}
    </span>
  )
}

function CategoryPills({ categories }: { categories: string[] }) {
  if (categories.length === 0) return <span className="text-[var(--color-muted)]">—</span>
  return (
    <div className="flex flex-wrap gap-1.5">
      {categories.map((category) => (
        <span
          key={category}
          className="inline-block rounded-full border border-[var(--color-border)] px-2 py-0.5 text-xs text-[var(--color-body)]"
        >
          {category}
        </span>
      ))}
    </div>
  )
}

export function LiveFeed() {
  const [state, setState] = useState<LoadState>({ status: 'loading' })
  const [paused, setPaused] = useState(false)
  const [staleError, setStaleError] = useState<string | null>(null)
  const [newIds, setNewIds] = useState<Set<string>>(new Set())
  const pausedRef = useRef(paused)
  const knownIdsRef = useRef<Set<string>>(new Set())

  useEffect(() => {
    pausedRef.current = paused
  }, [paused])

  const poll = useCallback(() => {
    fetchFeed()
      .then((data) => {
        const freshIds = new Set(data.map((entry) => entry.execution_id))
        const arrived: string[] = []
        for (const id of freshIds) {
          if (!knownIdsRef.current.has(id)) arrived.push(id)
        }
        knownIdsRef.current = freshIds

        setState({ status: 'ready', data })
        setStaleError(null)

        if (arrived.length > 0) {
          setNewIds((prev) => new Set([...prev, ...arrived]))
          setTimeout(() => {
            setNewIds((prev) => {
              const next = new Set(prev)
              arrived.forEach((id) => next.delete(id))
              return next
            })
          }, NEW_ROW_HIGHLIGHT_MS)
        }
      })
      .catch((error: unknown) => {
        const message = error instanceof Error ? error.message : 'Something went wrong.'
        // A background poll failure never wipes out data already on screen -
        // only the first load (no data yet) shows the full error state.
        setState((prev) => (prev.status === 'ready' ? prev : { status: 'error', message }))
        setStaleError(message)
      })
  }, [])

  useEffect(() => {
    poll()
    const interval = setInterval(() => {
      if (!pausedRef.current) poll()
    }, POLL_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [poll])

  function togglePaused() {
    setPaused((prev) => {
      const next = !prev
      if (!next) poll()
      return next
    })
  }

  return (
    <>
      <div className="border-b border-[var(--color-border)]">
        <div className="mx-auto flex max-w-6xl flex-wrap items-start justify-between gap-4 px-6 py-5">
          <div>
            <h1 className="text-xl font-medium text-[var(--color-ink)]">Live Feed</h1>
            <p className="mt-1 max-w-prose text-sm text-[var(--color-muted)]">
              The 25 most recent executions across every workload, refreshing automatically.
              Escalation-only blocks aren't shown here - they write no execution record (see the
              Sessions page for that caveat in full).
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-3">
            {paused && (
              <span className="rounded-full border border-[var(--color-border)] px-2.5 py-0.5 text-xs text-[var(--color-muted)]">
                Paused
              </span>
            )}
            <button
              type="button"
              onClick={togglePaused}
              className="rounded-sm border border-[var(--color-border)] px-3 py-1.5 text-sm text-[var(--color-body)] transition-colors duration-[var(--duration-base)] hover:border-[var(--color-accent)] hover:text-[var(--color-ink)]"
            >
              {paused ? 'Resume' : 'Pause'}
            </button>
          </div>
        </div>
      </div>

      <main className="mx-auto max-w-6xl px-6 py-8">
        {state.status === 'loading' && (
          <div role="status" className="py-24 text-center text-sm text-[var(--color-muted)]">
            Loading feed…
          </div>
        )}

        {state.status === 'error' && (
          <div
            role="alert"
            className="rounded-md border border-[var(--color-error)]/40 bg-[var(--color-surface)] p-6 text-center"
          >
            <p className="font-medium text-[var(--color-error)]">Couldn't load the feed</p>
            <p className="mt-1 text-sm text-[var(--color-muted)]">{state.message}</p>
            <button
              type="button"
              onClick={poll}
              className="mt-4 rounded-sm border border-[var(--color-border)] px-3 py-1.5 text-sm text-[var(--color-body)] hover:border-[var(--color-accent)] hover:text-[var(--color-ink)]"
            >
              Try again
            </button>
          </div>
        )}

        {state.status === 'ready' && (
          <>
            {staleError && (
              <p
                role="status"
                className="mb-4 text-sm text-[var(--color-muted)]"
              >
                Last refresh failed ({staleError}) - showing the most recent data received.
              </p>
            )}

            {state.data.length === 0 ? (
              <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] p-12 text-center">
                <p className="text-[var(--color-ink)]">No executions yet</p>
                <p className="mt-1 text-sm text-[var(--color-muted)]">
                  Send a request through the proxy and it will appear here automatically.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto rounded-md border border-[var(--color-border)] bg-[var(--color-surface)]">
                <table className="w-full min-w-[900px] border-collapse text-left text-sm">
                  <thead>
                    <tr className="border-b border-[var(--color-border)] text-xs text-[var(--color-muted)]">
                      <th scope="col" className="px-4 py-3 font-medium">
                        Time
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Session
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Workload
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Verdict
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Categories
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Tokens
                      </th>
                      <th scope="col" className="px-4 py-3 font-medium">
                        Latency
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {state.data.map((entry) => (
                      <tr
                        key={entry.execution_id}
                        className={`border-b border-[var(--color-border)] transition-colors duration-1000 last:border-0 ${
                          newIds.has(entry.execution_id)
                            ? 'border-l-2 border-l-[var(--color-accent)] bg-[var(--color-accent)]/5'
                            : ''
                        }`}
                      >
                        <td className="px-4 py-3 text-[var(--color-muted)]">
                          {new Date(entry.created_at).toLocaleTimeString()}
                        </td>
                        <td className="px-4 py-3">
                          <Link
                            to={`/sessions/${entry.session_id}`}
                            className="text-[var(--color-accent)] underline-offset-2 hover:underline"
                            title={entry.session_id}
                          >
                            {displayId(entry.session_id)}
                          </Link>
                        </td>
                        <td className="px-4 py-3 text-[var(--color-body)]" title={entry.workload_id}>
                          {displayId(entry.workload_id, entry.workload_name)}
                        </td>
                        <td className="px-4 py-3">
                          <BlockedBadge blocked={entry.blocked} />
                        </td>
                        <td className="px-4 py-3">
                          <CategoryPills categories={entry.categories} />
                        </td>
                        <td className="px-4 py-3 tabular-nums text-[var(--color-body)]">
                          {entry.tokens != null ? entry.tokens.toLocaleString() : '—'}
                        </td>
                        <td className="px-4 py-3 tabular-nums text-[var(--color-body)]">
                          {entry.latency_ms != null ? `${entry.latency_ms.toLocaleString()} ms` : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </main>
    </>
  )
}
