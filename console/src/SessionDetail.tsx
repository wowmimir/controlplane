import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { fetchSessionDetail, NotFoundError } from './api'
import { DispositionBadge } from './components/DispositionBadge'
import { displayId, isLedgerLive } from './lib/format'
import type { ExecutionOut, FindingOut, SessionDetail as SessionDetailData } from './types'

type LoadState =
  | { status: 'loading' }
  | { status: 'not-found' }
  | { status: 'error'; message: string }
  | { status: 'ready'; data: SessionDetailData }

// Matches app/redis_client.py's STRIKE_CATEGORIES order exactly, so the
// ledger summary always shows all six categories in the same fixed order.
const STRIKE_CATEGORIES = [
  'pii',
  'hallucination',
  'toxicity',
  'bias',
  'prompt_injection',
  'custom_policy',
]

function StrikeBadge({ category, count }: { category: string; count: number }) {
  const active = count > 0
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs ${
        active
          ? 'border-[var(--color-error)]/40 text-[var(--color-error)]'
          : 'border-[var(--color-border)] text-[var(--color-muted)]'
      }`}
    >
      {category} <span className="tabular-nums font-medium">{count}</span>
    </span>
  )
}

function FindingRow({ finding }: { finding: FindingOut }) {
  const maskedExcerpt = finding.evidence_ref?.masked_excerpt
  return (
    <li className="border-t border-[var(--color-border)] px-4 py-3 text-sm first:border-t-0">
      <div className="flex flex-wrap items-center gap-3">
        <span className="inline-block rounded-full border border-[var(--color-border)] px-2.5 py-0.5 text-xs text-[var(--color-body)]">
          {finding.category}
        </span>
        <span className="text-[var(--color-muted)]">
          confidence <span className="tabular-nums text-[var(--color-body)]">{finding.confidence.toFixed(2)}</span>
        </span>
        <span className="text-[var(--color-muted)]">
          {finding.evaluator_tier} tier
          {finding.evidence_ref?.side ? ` · ${finding.evidence_ref.side}` : ''}
        </span>
        <span className="ml-auto text-xs text-[var(--color-muted)]">
          {new Date(finding.timestamp).toLocaleString()}
        </span>
      </div>
      {maskedExcerpt ? (
        // 8.5: the text that tripped the rule, with the sensitive span
        // already blanked. Never the raw match.
        <p className="mt-2 overflow-x-auto whitespace-pre-wrap break-words rounded-sm border border-[var(--color-border)] bg-[var(--color-canvas)] px-2.5 py-1.5 font-mono text-xs text-[var(--color-muted)]">
          {maskedExcerpt}
        </p>
      ) : null}
    </li>
  )
}

function ExecutionCard({ execution, index }: { execution: ExecutionOut; index: number }) {
  return (
    <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)]">
      <div className="flex flex-wrap items-center gap-4 px-4 py-3">
        <span className="text-sm font-medium text-[var(--color-ink)]">Turn {index + 1}</span>
        <DispositionBadge disposition={execution.disposition} />
        {execution.model ? (
          <span className="inline-block rounded-sm border border-[var(--color-border)] px-1.5 py-0.5 font-mono text-xs text-[var(--color-body)]">
            {execution.model}
          </span>
        ) : null}
        <span className="text-sm text-[var(--color-muted)]">
          {execution.tokens != null ? `${execution.tokens.toLocaleString()} tokens` : 'no model call'}
          {execution.latency_ms != null ? ` · ${execution.latency_ms.toLocaleString()} ms` : ''}
          {execution.governance_overhead_ms != null
            ? ` · ${execution.governance_overhead_ms.toLocaleString()} ms governance`
            : ''}
        </span>
        <span className="ml-auto text-xs text-[var(--color-muted)]">
          {new Date(execution.created_at).toLocaleString()}
        </span>
      </div>
      {execution.findings.length > 0 ? (
        <ul>
          {execution.findings.map((finding) => (
            <FindingRow key={finding.finding_id} finding={finding} />
          ))}
        </ul>
      ) : (
        <p className="border-t border-[var(--color-border)] px-4 py-3 text-sm text-[var(--color-muted)]">
          No findings on this turn.
        </p>
      )}
    </div>
  )
}

export function SessionDetail() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const [state, setState] = useState<LoadState>({ status: 'loading' })

  const load = useCallback(() => {
    if (!sessionId) return
    setState({ status: 'loading' })
    fetchSessionDetail(sessionId)
      .then((data) => setState({ status: 'ready', data }))
      .catch((error: unknown) => {
        if (error instanceof NotFoundError) {
          setState({ status: 'not-found' })
          return
        }
        setState({
          status: 'error',
          message: error instanceof Error ? error.message : 'Something went wrong.',
        })
      })
  }, [sessionId])

  useEffect(() => {
    load()
  }, [load])

  return (
    <>
      <div className="border-b border-[var(--color-border)]">
        <div className="mx-auto max-w-6xl px-6 py-5">
          <Link
            to="/sessions"
            className="text-sm text-[var(--color-muted)] hover:text-[var(--color-ink)]"
          >
            ← Sessions
          </Link>
          <h1 className="mt-2 text-xl font-medium text-[var(--color-ink)]" title={sessionId}>
            {state.status === 'ready' ? displayId(state.data.session_id) : 'Session'}
          </h1>
          {state.status === 'ready' && (
            <p className="mt-1 text-sm text-[var(--color-muted)]">
              Workload {displayId(state.data.workload_id, state.data.workload_name)} · created{' '}
              {new Date(state.data.created_at).toLocaleString()}
            </p>
          )}
        </div>
      </div>

      <main className="mx-auto max-w-6xl px-6 py-8">
        {state.status === 'loading' && (
          <div role="status" className="py-24 text-center text-sm text-[var(--color-muted)]">
            Loading session…
          </div>
        )}

        {state.status === 'not-found' && (
          <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] p-12 text-center">
            <p className="text-[var(--color-ink)]">Session not found</p>
            <p className="mt-1 text-sm text-[var(--color-muted)]">
              No session matches that id. Double-check it was pasted in full.
            </p>
          </div>
        )}

        {state.status === 'error' && (
          <div
            role="alert"
            className="rounded-md border border-[var(--color-error)]/40 bg-[var(--color-surface)] p-6 text-center"
          >
            <p className="font-medium text-[var(--color-error)]">Couldn't load this session</p>
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
            {state.data.escalated && (() => {
              // 7.1/M3: cumulative_risk/strikes come from the Postgres
              // mirror, which never expires - but the Redis ledger that
              // actually gates traffic has a 15-minute TTL. Once it expires,
              // "new turns block immediately" is no longer true, so the
              // banner must say so. See docs/reviews/2026-08-25-phase6.md
              // Major #3.
              const ledgerLive = isLedgerLive(state.data.ttl_expires_at)
              return (
                <div
                  role="alert"
                  className="rounded-md border border-[var(--color-error)]/40 bg-[var(--color-surface)] p-4"
                >
                  <p className="font-medium text-[var(--color-error)]">
                    {ledgerLive ? 'This session is escalated' : 'This session was escalated'}
                  </p>
                  <p className="mt-1 text-sm text-[var(--color-muted)]">
                    Cumulative risk or a per-category strike count crossed Fork #3's threshold.{' '}
                    {ledgerLive
                      ? 'New turns on this session block immediately.'
                      : "The live ledger has since expired (15 minutes of inactivity) — a new turn today would start fresh."}{' '}
                    Escalation itself writes no execution row, so the turn that tripped it may not
                    be one of the ones listed below — the story here is the accumulation across
                    turns, not necessarily any single one of them.
                  </p>
                </div>
              )
            })()}

            <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
              <dl className="flex flex-wrap items-baseline gap-x-8 gap-y-4">
                <div>
                  <dt className="text-sm text-[var(--color-muted)]">Cumulative risk</dt>
                  <dd className="mt-1 text-3xl font-bold tabular-nums text-[var(--color-ink)]">
                    {state.data.cumulative_risk.toFixed(2)}
                  </dd>
                </div>
                <div>
                  <dt className="text-sm text-[var(--color-muted)]">Executions</dt>
                  <dd className="mt-1 text-3xl font-bold tabular-nums text-[var(--color-ink)]">
                    {state.data.execution_count}
                  </dd>
                </div>
              </dl>
              <div className="mt-5">
                <p className="mb-2 text-sm text-[var(--color-muted)]">Strikes per category</p>
                <div className="flex flex-wrap gap-2">
                  {STRIKE_CATEGORIES.map((category) => (
                    <StrikeBadge
                      key={category}
                      category={category}
                      count={state.data.strikes[category] ?? 0}
                    />
                  ))}
                </div>
              </div>
            </div>

            <div>
              <h2 className="mb-3 text-sm font-medium text-[var(--color-muted)]">
                Executions, oldest first
              </h2>
              {state.data.executions.length === 0 ? (
                <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] p-8 text-center text-sm text-[var(--color-muted)]">
                  No executions recorded for this session.
                </div>
              ) : (
                <div className="flex flex-col gap-3">
                  {state.data.executions.map((execution, index) => (
                    <ExecutionCard key={execution.execution_id} execution={execution} index={index} />
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </main>
    </>
  )
}
