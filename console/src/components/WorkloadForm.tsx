import { useEffect, useRef, useState, type FormEvent } from 'react'
import { createWorkload, updateWorkload } from '../api'
import type { FailMode, PolicyProfile, Workload, WorkloadCreate } from '../types'

interface WorkloadFormProps {
  open: boolean
  workload: Workload | null
  onClose: () => void
  onSaved: (workload: Workload) => void
}

const POLICY_PROFILES: PolicyProfile[] = ['strict', 'balanced', 'fast']
const FAIL_MODES: FailMode[] = ['fail_open', 'fail_closed']

const fieldClass =
  'rounded-sm border border-[var(--color-border)] bg-[var(--color-canvas)] px-3 py-2 text-sm text-[var(--color-ink)] outline-none focus-visible:border-[var(--color-accent)] focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]/40'
const labelClass = 'flex flex-col gap-1 text-sm'
const labelTextClass = 'text-[var(--color-muted)]'

export function WorkloadForm({ open, workload, onClose, onSaved }: WorkloadFormProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const isEdit = workload !== null

  const [name, setName] = useState('')
  const [geography, setGeography] = useState('')
  const [industry, setIndustry] = useState('')
  const [policyProfile, setPolicyProfile] = useState<PolicyProfile>('balanced')
  const [failMode, setFailMode] = useState<FailMode>('fail_open')
  const [latencyBudgetMs, setLatencyBudgetMs] = useState('1000')
  const [costBudget, setCostBudget] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setName(workload?.metadata?.name ?? '')
    setGeography(workload?.metadata?.geography ?? '')
    setIndustry(workload?.metadata?.industry ?? '')
    setPolicyProfile(workload?.policy_profile ?? 'balanced')
    setFailMode(workload?.fail_mode ?? 'fail_open')
    setLatencyBudgetMs(String(workload?.latency_budget_ms ?? 1000))
    setCostBudget(
      workload?.cost_budget_per_request != null ? String(workload.cost_budget_per_request) : '',
    )
    setError(null)
  }, [open, workload])

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open && !dialog.open) {
      dialog.showModal()
    } else if (!open && dialog.open) {
      dialog.close()
    }
  }, [open])

  // 7.1/N1: start from the workload's existing metadata (preserving any key
  // this form doesn't manage - e.g. one set via the API) and only set/clear
  // the three keys this form actually owns, instead of rebuilding the whole
  // object from scratch (which silently dropped unknown keys, and sent
  // `null` outright if all three managed fields were blank). See
  // docs/reviews/2026-08-25-phase6.md Minor, Editing a workload silently
  // destroys unknown metadata keys.
  function buildMetadata(): Record<string, unknown> | null {
    const metadata: Record<string, unknown> = { ...(workload?.metadata ?? {}) }
    const setOrClear = (key: string, value: string) => {
      const trimmed = value.trim()
      if (trimmed) metadata[key] = trimmed
      else delete metadata[key]
    }
    setOrClear('name', name)
    setOrClear('geography', geography)
    setOrClear('industry', industry)
    return Object.keys(metadata).length > 0 ? metadata : null
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)

    const payload: WorkloadCreate = {
      policy_profile: policyProfile,
      fail_mode: failMode,
      latency_budget_ms: Number(latencyBudgetMs),
      cost_budget_per_request: costBudget.trim() ? Number(costBudget) : null,
      metadata: buildMetadata(),
    }

    try {
      const saved =
        isEdit && workload
          ? await updateWorkload(workload.workload_id, payload)
          : await createWorkload(payload)
      onSaved(saved)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <dialog
      ref={dialogRef}
      onClose={onClose}
      onClick={(event) => {
        if (event.target === dialogRef.current) onClose()
      }}
      aria-labelledby="workload-form-title"
      className="w-full max-w-md rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] p-0 text-[var(--color-body)] backdrop:bg-[var(--color-canvas)]/80"
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-5 p-6">
        <div className="flex items-center justify-between">
          <h2 id="workload-form-title" className="text-lg font-medium text-[var(--color-ink)]">
            {isEdit ? 'Edit workload' : 'New workload'}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-sm px-2 py-1 text-[var(--color-muted)] hover:text-[var(--color-ink)]"
          >
            <span aria-hidden="true">×</span>
          </button>
        </div>

        {error ? (
          <p
            role="alert"
            className="rounded-sm border border-[var(--color-error)]/40 bg-[var(--color-canvas)] p-3 text-sm text-[var(--color-error)]"
          >
            {error}
          </p>
        ) : null}

        <label className={labelClass}>
          <span className={labelTextClass}>Name (optional)</span>
          <input
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="e.g. EU strict tier"
            autoFocus
            className={fieldClass}
          />
        </label>

        <p className="-mb-2 text-xs text-[var(--color-muted)]">
          Policy profile and the two budget fields below are recorded but not yet enforced by the
          evaluation path; only fail mode changes ControlPlane's behavior today.
        </p>

        <div className="grid grid-cols-2 gap-4">
          <label className={labelClass}>
            <span className={labelTextClass}>Policy profile</span>
            <select
              value={policyProfile}
              onChange={(event) => setPolicyProfile(event.target.value as PolicyProfile)}
              className={fieldClass}
            >
              {POLICY_PROFILES.map((profile) => (
                <option key={profile} value={profile}>
                  {profile}
                </option>
              ))}
            </select>
          </label>
          <label className={labelClass}>
            <span className={labelTextClass}>Fail mode</span>
            <select
              value={failMode}
              onChange={(event) => setFailMode(event.target.value as FailMode)}
              className={fieldClass}
            >
              {FAIL_MODES.map((mode) => (
                <option key={mode} value={mode}>
                  {mode}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <label className={labelClass}>
            <span className={labelTextClass}>Latency budget (ms)</span>
            <input
              type="number"
              min={1}
              required
              value={latencyBudgetMs}
              onChange={(event) => setLatencyBudgetMs(event.target.value)}
              className={fieldClass}
            />
          </label>
          <label className={labelClass}>
            <span className={labelTextClass}>Cost budget / request (optional)</span>
            <input
              type="number"
              min={0}
              step="0.01"
              value={costBudget}
              onChange={(event) => setCostBudget(event.target.value)}
              placeholder="e.g. 0.10"
              className={fieldClass}
            />
          </label>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <label className={labelClass}>
            <span className={labelTextClass}>Geography (optional)</span>
            <input
              type="text"
              value={geography}
              onChange={(event) => setGeography(event.target.value)}
              className={fieldClass}
            />
          </label>
          <label className={labelClass}>
            <span className={labelTextClass}>Industry (optional)</span>
            <input
              type="text"
              value={industry}
              onChange={(event) => setIndustry(event.target.value)}
              className={fieldClass}
            />
          </label>
        </div>

        <p className="-mt-1 text-xs text-[var(--color-muted)]">
          Per-category cheap-tier overrides (disable a category, raise a confidence floor, suppress a
          pattern) are set via the API or{' '}
          <code className="text-[var(--color-body)]">scripts/simulate_use_cases.py</code> for now, and
          shown read-only in the table. Editing here preserves any that are already set.
        </p>

        <div className="mt-2 flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-sm border border-[var(--color-border)] px-3 py-1.5 text-sm text-[var(--color-body)] transition-colors duration-[var(--duration-base)] hover:border-[var(--color-accent)] hover:text-[var(--color-ink)]"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="rounded-sm bg-[var(--color-accent)] px-3 py-1.5 text-sm font-medium text-[var(--color-on-accent)] transition-opacity duration-[var(--duration-base)] hover:opacity-90 disabled:opacity-50"
          >
            {submitting ? 'Saving…' : isEdit ? 'Save changes' : 'Create workload'}
          </button>
        </div>
      </form>
    </dialog>
  )
}
