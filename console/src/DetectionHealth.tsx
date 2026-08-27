import { useCallback, useEffect, useState } from 'react'
import { fetchDetectionHealth, fetchWorkloads, updateWorkload } from './api'
import { displayId } from './lib/format'
import type { CategoryOverride, DetectionHealthPattern, Workload, WorkloadMetadata } from './types'

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; patterns: DetectionHealthPattern[]; workloads: Workload[] }

// A row keyed `<category>:<tier>` (e.g. `hallucination:expensive`) is the
// expensive-tier judge, which has no `evidence_ref.pattern` for 8.6's filter
// to match - so it can't be suppressed per pattern.
function isSuppressable(pattern: string): boolean {
  return !pattern.includes(':')
}

// Build a full metadata object with `pattern` added to (or removed from)
// category_overrides[category].disabled_patterns, pruning empty containers so
// the Workloads "Overrides" column stays tidy. update_workload replaces
// metadata wholesale, so this must return the complete object.
function withPattern(
  metadata: WorkloadMetadata | null,
  category: string,
  pattern: string,
  action: 'add' | 'remove',
): WorkloadMetadata | null {
  const base: WorkloadMetadata = { ...(metadata ?? {}) }
  const overrides: Record<string, CategoryOverride> = { ...(base.category_overrides ?? {}) }
  const rule: CategoryOverride = { ...(overrides[category] ?? {}) }
  const current = Array.isArray(rule.disabled_patterns) ? rule.disabled_patterns : []
  const next =
    action === 'add'
      ? current.includes(pattern)
        ? current
        : [...current, pattern]
      : current.filter((p) => p !== pattern)

  if (next.length > 0) {
    rule.disabled_patterns = next
  } else {
    delete rule.disabled_patterns
  }

  if (Object.keys(rule).length > 0) {
    overrides[category] = rule
  } else {
    delete overrides[category]
  }

  if (Object.keys(overrides).length > 0) {
    base.category_overrides = overrides
  } else {
    delete base.category_overrides
  }

  return Object.keys(base).length > 0 ? base : null
}

function SuppressControl({
  row,
  workloads,
  onChanged,
}: {
  row: DetectionHealthPattern
  workloads: Workload[]
  onChanged: () => void
}) {
  const candidates = workloads.filter((w) => !row.suppressed_by.includes(w.workload_id))
  const [target, setTarget] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function apply(workloadId: string, action: 'add' | 'remove') {
    const workload = workloads.find((w) => w.workload_id === workloadId)
    if (!workload || pending) return
    setPending(true)
    setError(null)
    try {
      await updateWorkload(workloadId, {
        metadata: withPattern(workload.metadata, row.category, row.pattern, action),
      })
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save.')
    } finally {
      setPending(false)
    }
  }

  if (!isSuppressable(row.pattern)) {
    return <span className="text-xs text-[var(--color-muted)]">not per-pattern suppressible</span>
  }

  return (
    <div className="flex flex-col gap-1.5">
      {row.suppressed_by.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {row.suppressed_by.map((workloadId) => {
            const workload = workloads.find((w) => w.workload_id === workloadId)
            return (
              <span
                key={workloadId}
                className="inline-flex items-center gap-1.5 rounded-full border border-[var(--color-info)]/40 px-2 py-0.5 text-xs text-[var(--color-info)]"
              >
                {displayId(workloadId, workload?.metadata?.name)}
                <button
                  type="button"
                  disabled={pending}
                  onClick={() => apply(workloadId, 'remove')}
                  className="text-[var(--color-muted)] hover:text-[var(--color-ink)] disabled:opacity-50"
                  aria-label="Stop suppressing for this workload"
                >
                  <span aria-hidden="true">×</span>
                </button>
              </span>
            )
          })}
        </div>
      ) : null}
      {candidates.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1.5">
          <label className="sr-only" htmlFor={`suppress-${row.pattern}`}>
            Suppress {row.pattern} for a workload
          </label>
          <select
            id={`suppress-${row.pattern}`}
            value={target}
            onChange={(event) => setTarget(event.target.value)}
            className="rounded-sm border border-[var(--color-border)] bg-[var(--color-canvas)] px-2 py-1 text-xs text-[var(--color-ink)] outline-none focus-visible:border-[var(--color-accent)]"
          >
            <option value="">Suppress for workload…</option>
            {candidates.map((workload) => (
              <option key={workload.workload_id} value={workload.workload_id}>
                {displayId(workload.workload_id, workload.metadata?.name)}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={!target || pending}
            onClick={() => apply(target, 'add')}
            className="rounded-sm border border-[var(--color-border)] px-2 py-1 text-xs text-[var(--color-body)] transition-colors duration-[var(--duration-base)] hover:border-[var(--color-accent)] hover:text-[var(--color-ink)] disabled:opacity-50"
          >
            Suppress
          </button>
        </div>
      ) : null}
      {error ? <span className="text-xs text-[var(--color-error)]">{error}</span> : null}
    </div>
  )
}

export function DetectionHealth() {
  const [state, setState] = useState<LoadState>({ status: 'loading' })

  const load = useCallback(() => {
    setState((prev) => (prev.status === 'ready' ? prev : { status: 'loading' }))
    Promise.all([fetchDetectionHealth(), fetchWorkloads()])
      .then(([patterns, workloads]) => setState({ status: 'ready', patterns, workloads }))
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
        <div className="mx-auto flex max-w-6xl flex-wrap items-start justify-between gap-4 px-6 py-5">
          <div>
            <h1 className="text-xl font-medium text-[var(--color-ink)]">Detection health</h1>
            <p className="mt-1 max-w-prose text-sm text-[var(--color-muted)]">
              Every detection pattern's false-positive rate, from the findings operators have
              actually reviewed, aggregated across all workloads. A pattern that fires wrong too
              often is flagged, and you can suppress it for the one workload where it's noisy
              without losing the rest of that category's coverage.
            </p>
          </div>
          <button
            type="button"
            onClick={load}
            disabled={state.status === 'loading'}
            className="shrink-0 rounded-sm border border-[var(--color-border)] px-3 py-1.5 text-sm text-[var(--color-body)] transition-colors duration-[var(--duration-base)] hover:border-[var(--color-accent)] hover:text-[var(--color-ink)] disabled:opacity-50"
          >
            {state.status === 'loading' ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>

      <main className="mx-auto max-w-6xl px-6 py-8">
        {state.status === 'loading' && (
          <div role="status" className="py-24 text-center text-sm text-[var(--color-muted)]">
            Loading detection health…
          </div>
        )}

        {state.status === 'error' && (
          <div
            role="alert"
            className="rounded-md border border-[var(--color-error)]/40 bg-[var(--color-surface)] p-6 text-center"
          >
            <p className="font-medium text-[var(--color-error)]">Couldn't load detection health</p>
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

        {state.status === 'ready' && state.patterns.length === 0 && (
          <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] p-12 text-center">
            <p className="text-[var(--color-ink)]">No findings yet</p>
            <p className="mt-1 text-sm text-[var(--color-muted)]">
              Once the proxy records some findings and operators review them, each pattern's
              false-positive rate shows up here.
            </p>
          </div>
        )}

        {state.status === 'ready' && state.patterns.length > 0 && (
          <div className="overflow-x-auto rounded-md border border-[var(--color-border)] bg-[var(--color-surface)]">
            <table className="w-full min-w-[980px] border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-xs text-[var(--color-muted)]">
                  <th scope="col" className="px-4 py-3 font-medium">Pattern</th>
                  <th scope="col" className="px-4 py-3 font-medium">Category</th>
                  <th scope="col" className="px-4 py-3 font-medium">Confirmed</th>
                  <th scope="col" className="px-4 py-3 font-medium">False positive</th>
                  <th scope="col" className="px-4 py-3 font-medium">Unreviewed</th>
                  <th scope="col" className="px-4 py-3 font-medium">FP rate</th>
                  <th scope="col" className="px-4 py-3 font-medium">Suppression</th>
                </tr>
              </thead>
              <tbody>
                {state.patterns.map((row) => (
                  <tr
                    key={row.pattern}
                    className={`border-b border-[var(--color-border)] align-top last:border-0 ${
                      row.needs_attention ? 'bg-[var(--color-error)]/5' : ''
                    }`}
                  >
                    <td className="px-4 py-3 font-mono text-xs text-[var(--color-body)]">
                      {row.pattern}
                      {row.needs_attention ? (
                        <span className="ml-2 inline-block rounded-full border border-[var(--color-error)]/40 px-2 py-0.5 font-sans text-xs font-medium text-[var(--color-error)]">
                          needs attention
                        </span>
                      ) : null}
                    </td>
                    <td className="px-4 py-3 text-[var(--color-body)]">{row.category}</td>
                    <td className="px-4 py-3 tabular-nums text-[var(--color-body)]">{row.confirmed}</td>
                    <td className="px-4 py-3 tabular-nums text-[var(--color-body)]">
                      {row.false_positive}
                    </td>
                    <td className="px-4 py-3 tabular-nums text-[var(--color-muted)]">{row.unreviewed}</td>
                    <td className="px-4 py-3 tabular-nums text-[var(--color-body)]">
                      {row.false_positive_rate != null ? (
                        <span className={row.needs_attention ? 'text-[var(--color-error)]' : undefined}>
                          {Math.round(row.false_positive_rate * 100)}%
                          <span className="ml-1 text-xs text-[var(--color-muted)]">
                            ({row.reviewed} reviewed)
                          </span>
                        </span>
                      ) : (
                        <span className="text-[var(--color-muted)]">— (0 reviewed)</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <SuppressControl row={row} workloads={state.workloads} onChanged={load} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {state.status === 'ready' && state.patterns.length > 0 ? (
          <p className="mt-4 text-xs text-[var(--color-muted)]">
            A pattern is flagged "needs attention" at a false-positive rate of 30% or higher over at
            least 5 reviewed findings. Suppressing a pattern for a workload drops it before it
            becomes a finding there, so it stops blocking, striking, and showing up in that
            workload's audit trail entirely — a real coverage cut the operator owns.
          </p>
        ) : null}
      </main>
    </>
  )
}
