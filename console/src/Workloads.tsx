import { useCallback, useEffect, useState } from 'react'
import { fetchWorkloads } from './api'
import { WorkloadForm } from './components/WorkloadForm'
import { displayId, formatCategoryOverrides } from './lib/format'
import type { Workload } from './types'

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: Workload[] }

type FormState = { open: boolean; workload: Workload | null }

function Badge({ children }: { children: string }) {
  return (
    <span className="inline-block rounded-full border border-[var(--color-border)] px-2.5 py-0.5 text-xs text-[var(--color-body)]">
      {children}
    </span>
  )
}

export function Workloads() {
  const [state, setState] = useState<LoadState>({ status: 'loading' })
  const [form, setForm] = useState<FormState>({ open: false, workload: null })

  const load = useCallback(() => {
    setState({ status: 'loading' })
    fetchWorkloads()
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

  function handleSaved() {
    load()
  }

  return (
    <>
      <div className="border-b border-[var(--color-border)]">
        <div className="mx-auto flex max-w-6xl flex-wrap items-start justify-between gap-4 px-6 py-5">
          <div>
            <h1 className="text-xl font-medium text-[var(--color-ink)]">Workloads</h1>
            <p className="mt-1 max-w-prose text-sm text-[var(--color-muted)]">
              Each workload carries its own policy profile, latency and cost budgets, and fail
              mode. A request with no <code className="text-[var(--color-body)]">X-Workload-Id</code>{' '}
              header falls back to the default workload below.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setForm({ open: true, workload: null })}
            className="shrink-0 rounded-sm bg-[var(--color-accent)] px-3 py-1.5 text-sm font-medium text-[var(--color-on-accent)] transition-opacity duration-[var(--duration-base)] hover:opacity-90"
          >
            New workload
          </button>
        </div>
      </div>

      <main className="mx-auto max-w-6xl px-6 py-8">
        {state.status === 'loading' && (
          <div role="status" className="py-24 text-center text-sm text-[var(--color-muted)]">
            Loading workloads…
          </div>
        )}

        {state.status === 'error' && (
          <div
            role="alert"
            className="rounded-md border border-[var(--color-error)]/40 bg-[var(--color-surface)] p-6 text-center"
          >
            <p className="font-medium text-[var(--color-error)]">Couldn't load workloads</p>
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
            <p className="text-[var(--color-ink)]">No workloads yet</p>
            <p className="mt-1 text-sm text-[var(--color-muted)]">
              Create one to give a caller its own policy profile and budgets.
            </p>
          </div>
        )}

        {state.status === 'ready' && state.data.length > 0 && (
          <div className="overflow-x-auto rounded-md border border-[var(--color-border)] bg-[var(--color-surface)]">
            <table className="w-full min-w-[860px] border-collapse text-left text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-xs text-[var(--color-muted)]">
                  <th scope="col" className="px-4 py-3 font-medium">
                    Workload
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Policy profile
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Fail mode
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Latency budget
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Cost budget
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Overrides
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    Created
                  </th>
                  <th scope="col" className="px-4 py-3 font-medium">
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {state.data.map((workload) => (
                  <tr
                    key={workload.workload_id}
                    className="border-b border-[var(--color-border)] last:border-0"
                  >
                    <td className="px-4 py-3">
                      <span
                        className="text-[var(--color-ink)]"
                        title={workload.workload_id}
                      >
                        {displayId(workload.workload_id, workload.metadata?.name)}
                      </span>
                      {workload.workload_id === '00000000-0000-0000-0000-000000000000' ? (
                        <span className="ml-2 text-xs text-[var(--color-muted)]">(default)</span>
                      ) : null}
                    </td>
                    <td className="px-4 py-3">
                      <Badge>{workload.policy_profile}</Badge>
                    </td>
                    <td className="px-4 py-3">
                      <Badge>{workload.fail_mode}</Badge>
                    </td>
                    <td className="px-4 py-3 tabular-nums text-[var(--color-body)]">
                      {workload.latency_budget_ms.toLocaleString()} ms
                    </td>
                    <td className="px-4 py-3 tabular-nums text-[var(--color-body)]">
                      {workload.cost_budget_per_request != null
                        ? `$${workload.cost_budget_per_request.toFixed(2)}`
                        : '—'}
                    </td>
                    <td className="px-4 py-3 text-[var(--color-body)]">
                      {formatCategoryOverrides(workload.metadata) || '—'}
                    </td>
                    <td className="px-4 py-3 text-[var(--color-muted)]">
                      {new Date(workload.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => setForm({ open: true, workload })}
                        className="rounded-sm border border-[var(--color-border)] px-2.5 py-1 text-xs text-[var(--color-body)] transition-colors duration-[var(--duration-base)] hover:border-[var(--color-accent)] hover:text-[var(--color-ink)]"
                      >
                        Edit
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>

      <WorkloadForm
        open={form.open}
        workload={form.workload}
        onClose={() => setForm({ open: false, workload: null })}
        onSaved={handleSaved}
      />
    </>
  )
}
