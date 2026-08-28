import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { Link } from 'react-router-dom'
import { fetchWorkloads, sendChatCompletion } from './api'
import { displayId } from './lib/format'
import { DEFAULT_PLAYGROUND_MODEL, type ChatResult, type ChatTurn, type Workload } from './types'

// The seeded default workload (app/seed.py). fetchWorkloads() returns it like
// any other row, but the "Default workload" option already covers it (sending
// no X-Workload-Id resolves to the same row), so it's filtered out of the list
// to avoid showing it twice.
const DEFAULT_WORKLOAD_ID = '00000000-0000-0000-0000-000000000000'

// Same input styling the workload form uses (console/src/components/WorkloadForm.tsx).
const fieldClass =
  'rounded-sm border border-[var(--color-border)] bg-[var(--color-canvas)] px-3 py-2 text-sm text-[var(--color-ink)] outline-none focus-visible:border-[var(--color-accent)] focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]/40'

function workloadLabel(workload: Workload): string {
  return workload.metadata?.name ?? `${workload.workload_id.slice(0, 8)}…`
}

function OutcomePanel({ outcome }: { outcome: Exclude<ChatResult, { kind: 'ok' }> }) {
  if (outcome.kind === 'escalated') {
    return (
      <div
        role="alert"
        className="rounded-md border border-[var(--color-warning)]/40 bg-[var(--color-surface)] p-4"
      >
        <p className="text-sm font-medium text-[var(--color-warning)]">
          Session blocked: accumulated risk
        </p>
        <p className="mt-1 text-sm text-[var(--color-body)]">{outcome.message}</p>
      </div>
    )
  }

  if (outcome.kind === 'blocked') {
    return (
      <div
        role="alert"
        className="rounded-md border border-[var(--color-error)]/40 bg-[var(--color-surface)] p-4"
      >
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-medium text-[var(--color-error)]">Blocked</p>
          <span className="inline-block rounded-full border border-[var(--color-border)] px-2 py-0.5 text-xs text-[var(--color-body)]">
            {outcome.code}
          </span>
        </div>
        <p className="mt-1 text-sm text-[var(--color-body)]">{outcome.message}</p>
      </div>
    )
  }

  return (
    <div
      role="alert"
      className="rounded-md border border-[var(--color-error)]/40 bg-[var(--color-surface)] p-4"
    >
      <p className="text-sm font-medium text-[var(--color-error)]">Something went wrong</p>
      <p className="mt-1 text-sm text-[var(--color-body)]">{outcome.message}</p>
    </div>
  )
}

export function Playground() {
  const [workloads, setWorkloads] = useState<Workload[]>([])
  const [workloadId, setWorkloadId] = useState<string | null>(null)
  const [model, setModel] = useState(DEFAULT_PLAYGROUND_MODEL)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [transcript, setTranscript] = useState<ChatTurn[]>([])
  const [prompt, setPrompt] = useState('')
  const [pending, setPending] = useState(false)
  const [outcome, setOutcome] = useState<Exclude<ChatResult, { kind: 'ok' }> | null>(null)

  const bottomRef = useRef<HTMLDivElement>(null)
  // Bumped whenever the conversation is reset or the workload switched. An
  // in-flight send() captures the value at dispatch and drops its result if it
  // no longer matches - otherwise a slow response could revive a session the
  // user just cleared, or land under the wrong workload (10.1 review M1).
  const genRef = useRef(0)

  useEffect(() => {
    fetchWorkloads()
      .then((rows) => setWorkloads(rows.filter((row) => row.workload_id !== DEFAULT_WORKLOAD_ID)))
      .catch(() => {
        // Best effort - the selector just stays at "Default workload" only.
      })
  }, [])

  useEffect(() => {
    if (transcript.length === 0 && outcome === null) return
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [transcript, outcome])

  const selectedName = useMemo(() => {
    if (workloadId === null) return 'the default workload'
    const found = workloads.find((row) => row.workload_id === workloadId)
    return found ? workloadLabel(found) : 'a workload'
  }, [workloadId, workloads])

  const isEmpty = transcript.length === 0 && sessionId === null && outcome === null

  function resetConversation() {
    genRef.current += 1
    setPending(false) // abort any in-flight send - its result is now ignored
    setSessionId(null)
    setTranscript([])
    setOutcome(null)
  }

  function changeWorkload(value: string) {
    // A session cannot span two workloads - the proxy returns 400 if a session
    // id is reused under a different one (forks.md Fork #1) - so switching the
    // workload has to start a fresh conversation.
    setWorkloadId(value === '' ? null : value)
    resetConversation()
  }

  async function send() {
    const text = prompt.trim()
    if (!text || pending) return

    const gen = genRef.current
    // A blocked turn stays visible but is NOT resent - the proxy never produced
    // a reply for it, and forwarding a blocked prompt to the model on a later
    // turn would contradict "blocked before the model is called" (10.1 review M2).
    const payload: ChatTurn[] = [
      ...transcript.filter((turn) => !turn.blocked).map(({ role, content }) => ({ role, content })),
      { role: 'user', content: text },
    ]
    setTranscript((prev) => [...prev, { role: 'user', content: text }])
    setPrompt('')
    setOutcome(null)
    setPending(true)
    try {
      const result = await sendChatCompletion({ model, messages: payload, workloadId, sessionId })
      if (gen !== genRef.current) return // conversation was reset / workload switched mid-flight

      if (result.kind === 'ok') {
        setTranscript((prev) => [...prev, { role: 'assistant', content: result.content }])
      } else {
        setOutcome(result)
        if (result.kind === 'blocked' || result.kind === 'escalated') {
          setTranscript((prev) =>
            prev.map((turn, i) => (i === prev.length - 1 ? { ...turn, blocked: true } : turn)),
          )
        }
        if (result.kind === 'error') {
          setPrompt(text) // a network / upstream failure - keep the text for a retry
        }
      }
      // Capture the session id off every outcome that carries one - the proxy
      // creates the Session row and sets the header even on a 403 or a 502.
      if (result.sessionId) {
        setSessionId(result.sessionId)
      }
    } finally {
      if (gen === genRef.current) setPending(false)
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.preventDefault()
      void send()
    }
  }

  return (
    <>
      <div className="border-b border-[var(--color-border)]">
        <div className="mx-auto flex max-w-6xl flex-wrap items-start justify-between gap-4 px-6 py-5">
          <div>
            <h1 className="text-xl font-medium text-[var(--color-ink)]">Playground</h1>
            <p className="mt-1 max-w-prose text-sm text-[var(--color-muted)]">
              Send prompts straight through the proxy from the browser, against {selectedName}. Every
              message reuses the session ControlPlane hands back, so risk carries across turns. Send
              a violation, then a clean prompt, and watch the second one get blocked on the session's
              built-up risk.
            </p>
          </div>
          <button
            type="button"
            onClick={resetConversation}
            disabled={isEmpty}
            className="shrink-0 rounded-sm border border-[var(--color-border)] px-3 py-1.5 text-sm text-[var(--color-body)] transition-colors duration-[var(--duration-base)] hover:border-[var(--color-accent)] hover:text-[var(--color-ink)] disabled:opacity-50"
          >
            New conversation
          </button>
        </div>
      </div>

      <main className="mx-auto max-w-6xl px-6 py-8">
        <div className="mb-6 flex flex-wrap items-end gap-4">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-[var(--color-muted)]">Workload</span>
            <select
              value={workloadId ?? ''}
              onChange={(event) => changeWorkload(event.target.value)}
              disabled={pending}
              className={`${fieldClass} disabled:opacity-50`}
            >
              <option value="">Default workload</option>
              {workloads.map((row) => (
                <option key={row.workload_id} value={row.workload_id}>
                  {workloadLabel(row)} ({row.policy_profile})
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1 text-sm">
            <span className="text-[var(--color-muted)]">Model</span>
            <input
              type="text"
              value={model}
              onChange={(event) => setModel(event.target.value)}
              className={`${fieldClass} font-mono`}
              size={24}
            />
          </label>

          <div className="flex flex-col gap-1 text-sm">
            <span className="text-[var(--color-muted)]">Session</span>
            <span className="px-1 py-2 text-sm">
              {sessionId ? (
                <Link
                  to={`/sessions/${sessionId}`}
                  title={sessionId}
                  className="text-[var(--color-accent)] underline-offset-2 hover:underline"
                >
                  {displayId(sessionId)}
                </Link>
              ) : (
                <span className="text-[var(--color-muted)]">starts on first send</span>
              )}
            </span>
          </div>
        </div>

        <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
          {transcript.length === 0 && outcome === null ? (
            <p className="py-16 text-center text-sm text-[var(--color-muted)]">
              Type a prompt below and hit Send (or Ctrl/Cmd + Enter).
            </p>
          ) : (
            <div className="flex flex-col gap-3">
              {transcript.map((turn, index) => (
                <div
                  key={index}
                  className={turn.role === 'user' ? 'flex flex-col items-end' : 'flex flex-col items-start'}
                >
                  <div
                    className={`max-w-[80%] whitespace-pre-wrap break-words rounded-md px-3 py-2 text-sm ${
                      turn.blocked
                        ? 'border border-dashed border-[var(--color-error)]/40 text-[var(--color-muted)]'
                        : turn.role === 'user'
                          ? 'bg-[var(--color-canvas)] text-[var(--color-body)]'
                          : 'border border-[var(--color-border)] text-[var(--color-ink)]'
                    }`}
                  >
                    {turn.content || (
                      <span className="text-[var(--color-muted)]">(empty response)</span>
                    )}
                  </div>
                  {turn.blocked && (
                    <span className="mt-0.5 text-xs text-[var(--color-muted)]">
                      blocked: not sent to the model, and not resent on the next turn
                    </span>
                  )}
                </div>
              ))}

              {pending && (
                <div role="status" className="flex justify-start">
                  <div className="rounded-md border border-[var(--color-border)] px-3 py-2 text-sm text-[var(--color-muted)]">
                    Evaluating…
                  </div>
                </div>
              )}

              {outcome && <OutcomePanel outcome={outcome} />}
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <form
          onSubmit={(event) => {
            event.preventDefault()
            void send()
          }}
          className="mt-4 flex flex-col gap-3"
        >
          <textarea
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            onKeyDown={handleKeyDown}
            rows={3}
            placeholder="Ask something, or try a prompt with an email address to see a cheap-tier block."
            className={`${fieldClass} resize-y`}
          />
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={pending || prompt.trim() === ''}
              className="rounded-sm bg-[var(--color-accent)] px-4 py-1.5 text-sm font-medium text-[var(--color-on-accent)] transition-opacity duration-[var(--duration-base)] hover:opacity-90 disabled:opacity-50"
            >
              {pending ? 'Sending…' : 'Send'}
            </button>
          </div>
        </form>
      </main>
    </>
  )
}
