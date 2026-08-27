import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchFindings } from './api'
import { DispositionBadge } from './components/DispositionBadge'
import { ReviewControls } from './components/ReviewControls'
import { displayId } from './lib/format'
import type { ReviewQueueEntry, ReviewStatus } from './types'

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: ReviewQueueEntry[] }

type Filter = ReviewStatus | 'all'

const FILTERS: { value: Filter; label: string }[] = [
  { value: 'unreviewed', label: 'Needs review' },
  { value: 'confirmed', label: 'Confirmed' },
  { value: 'false_positive', label: 'False positives' },
  { value: 'all', label: 'All' },
]

export function ReviewQueue() {
  const [filter, setFilter] = useState<Filter>('unreviewed')
  const [state, setState] = useState<LoadState>({ status: 'loading' })

  const load = useCallback(() => {
    setState({ status: 'loading' })
    fetchFindings(filter === 'all' ? undefined : { reviewStatus: filter })
      .then((data) => setState({ status: 'ready', data }))
      .catch((error: unknown) =>
        setState({
          status: 'error',
          message: error instanceof Error ? error.message : 'Something went wrong.',
        }),
      )
  }, [filter])

  useEffect(() => {
    load()
  }, [load])

  const handleReviewed = useCallback(
    (findingId: string, next: ReviewStatus) => {
      setState((prev) => {
        if (prev.status !== 'ready') return prev
        // On a status-scoped view, a row that no longer matches drops out;
        // on "All" it just updates in place.
        const data =
          filter !== 'all' && next !== filter
            ? prev.data.filter((row) => row.finding_id !== findingId)
            : prev.data.map((row) =>
                row.finding_id === findingId ? { ...row, review_status: next } : row,
              )
        return { ...prev, data }
      })
    },
    [filter],
  )

  return (
    <>
      <div className="border-b border-[var(--color-border)]">
        <div className="mx-auto flex max-w-6xl flex-wrap items-start justify-between gap-4 px-6 py-5">
          <div>
            <h1 className="text-xl font-medium text-[var(--color-ink)]">Review</h1>
            <p className="mt-1 max-w-prose text-sm text-[var(--color-muted)]">
              Every finding still waiting for an operator's verdict, newest first. Confirming or
              rejecting a finding here feeds the Dashboard's false-positive rate and the Detection
              Health page, so nobody has to trawl sessions one at a time.
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
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
        <div className="mb-5 flex flex-wrap gap-1" role="tablist" aria-label="Filter findings by review status">
          {FILTERS.map((option) => (
            <button
              key={option.value}
              type="button"
              role="tab"
              aria-selected={filter === option.value}
              onClick={() => setFilter(option.value)}
              className={`rounded-sm px-3 py-1.5 text-sm font-medium transition-colors duration-[var(--duration-base)] ${
                filter === option.value
                  ? 'bg-[var(--color-surface)] text-[var(--color-ink)]'
                  : 'text-[var(--color-muted)] hover:text-[var(--color-ink)]'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>

        {state.status === 'loading' && (
          <div role="status" className="py-24 text-center text-sm text-[var(--color-muted)]">
            Loading findings…
          </div>
        )}

        {state.status === 'error' && (
          <div
            role="alert"
            className="rounded-md border border-[var(--color-error)]/40 bg-[var(--color-surface)] p-6 text-center"
          >
            <p className="font-medium text-[var(--color-error)]">Couldn't load findings</p>
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
            <p className="text-[var(--color-ink)]">
              {filter === 'unreviewed' ? 'Nothing waiting for review' : 'No findings match this filter'}
            </p>
            <p className="mt-1 text-sm text-[var(--color-muted)]">
              {filter === 'unreviewed'
                ? 'Every finding so far has a verdict. New findings show up here as they come in.'
                : 'Try another filter, or confirm and reject some findings first.'}
            </p>
          </div>
        )}

        {state.status === 'ready' && state.data.length > 0 && (
          <div className="overflow-x-auto rounded-md border border-[var(--color-border)] bg-[var(--color-surface)]">
            <table className="w-full min-w-[960px] border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-xs text-[var(--color-muted)]">
                  <th scope="col" className="px-4 py-3 font-medium">Pattern</th>
                  <th scope="col" className="px-4 py-3 font-medium">Category</th>
                  <th scope="col" className="px-4 py-3 font-medium">Confidence</th>
                  <th scope="col" className="px-4 py-3 font-medium">Side</th>
                  <th scope="col" className="px-4 py-3 font-medium">Outcome</th>
                  <th scope="col" className="px-4 py-3 font-medium">Workload</th>
                  <th scope="col" className="px-4 py-3 font-medium">Session</th>
                  <th scope="col" className="px-4 py-3 font-medium">Review</th>
                </tr>
              </thead>
              <tbody>
                {state.data.map((row) => (
                  <tr
                    key={row.finding_id}
                    className="border-b border-[var(--color-border)] align-top last:border-0"
                  >
                    <td className="px-4 py-3 font-mono text-xs text-[var(--color-body)]">
                      {row.pattern ?? `${row.category}:${row.evaluator_tier}`}
                    </td>
                    <td className="px-4 py-3 text-[var(--color-body)]">{row.category}</td>
                    <td className="px-4 py-3 tabular-nums text-[var(--color-body)]">
                      {row.confidence.toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-[var(--color-muted)]">{row.side ?? '—'}</td>
                    <td className="px-4 py-3">
                      <DispositionBadge disposition={row.disposition} />
                    </td>
                    <td className="px-4 py-3 text-[var(--color-body)]" title={row.workload_id}>
                      {displayId(row.workload_id, row.workload_name)}
                    </td>
                    <td className="px-4 py-3">
                      <Link
                        to={`/sessions/${row.session_id}`}
                        title={row.session_id}
                        className="text-[var(--color-accent)] underline-offset-2 hover:underline"
                      >
                        {displayId(row.session_id)}
                      </Link>
                    </td>
                    <td className="px-4 py-3">
                      <ReviewControls
                        findingId={row.finding_id}
                        reviewStatus={row.review_status}
                        onReviewed={(next) => handleReviewed(row.finding_id, next)}
                      />
                      {row.masked_excerpt ? (
                        <p className="mt-2 max-w-md overflow-x-auto whitespace-pre-wrap break-words rounded-sm border border-[var(--color-border)] bg-[var(--color-canvas)] px-2.5 py-1.5 font-mono text-xs text-[var(--color-muted)]">
                          {row.masked_excerpt}
                        </p>
                      ) : null}
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
