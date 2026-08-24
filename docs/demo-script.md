# Demo video script

A shot list for recording ControlPlane's hackathon demo video. Built directly
on `scripts/seed_demo.py`'s four scenarios (already proven reliable, see
`.agents/prompts/6.1-seed-simulation-script-plan.md`) plus a tour of the four
console pages that render their results.

## Prerequisites

- Backend running (`uv run uvicorn app.main:app --reload --port 8000`)
- Console running (`cd console && npm run dev`, on `http://localhost:5173`)
- `.env` configured with real, working values

## Live vs. pre-seeded traffic

**Recommended: run `scripts/seed_demo.py` live, on camera**, during Shots 3-5
below. Its own printed narration doubles as on-screen proof to the audience
that this is real traffic, not staged data, and it's already been confirmed
to pass all four scenarios reliably in one run.

The one accepted risk: the async finding in Shot 5 can take up to ~45 seconds
to land. Start the script running *before* Shot 6 (the console tour) so that
wait isn't dead air — narrate the Dashboard and Workloads pages while the
script's poll loop runs in the background, then cut back to Session
Drilldown once it reports success.

**Fallback**, if a live take doesn't go cleanly: run the script a few minutes
before recording, then narrate from the already-populated console instead of
running it on camera. Either way, don't skip actually running it — the console
needs real data to show.

## Shot 1 — Introduce the project (10-15s)

No UI yet. One or two sentences: ControlPlane is an AI governance proxy — it
sits between an application and its model API, checks every request and
response against a policy taxonomy, and tracks risk across a whole session,
not just one message.

## Shot 2 — Clean pass

Run (or point at) `scripts/seed_demo.py`'s scenario 1: a benign question,
`200` back with a real model answer. Say: this is the baseline — nothing
suspicious, nothing blocks it, the model call goes straight through.

## Shot 3 — Cheap-tier block

Scenario 2: a prompt containing an email address. Call out the `403` and the
`error.code: "pii"` in the response. Say: this is blocked *before* the model
is ever called — the cheap tier is synchronous and fails fast, so a violation
never costs the latency or expense of a real model round trip.

## Shot 4 — Ledger-driven escalation

Scenario 3's two turns. Turn 1 trips a block on its own content. Turn 2, same
session, sends something completely clean — and still gets blocked. Narrate
this explicitly: the second block has nothing to do with what was just said;
it's the session's accumulated risk from turn 1 still over threshold. This is
the defensibility story — ControlPlane isn't just reacting to one message, it
remembers.

The proof for this shot is the terminal output itself (the script prints
turn 2's status and `error.type: "controlplane_session_escalated"`), not the
console — an escalation block has no per-turn content to attach evidence to,
so it writes no `Execution`/`Finding` row (see Shot 6's caveat on Session
Drilldown for this same session).

## Shot 5 — Async expensive-tier finding

Scenario 4: a request that releases immediately (`200`) — say so, and note
that from the caller's point of view, nothing about this looked risky. Then
cut to Session Drilldown for this session a few seconds later once the
script's poll reports success: a hallucination finding has landed, written
by an LLM judge that checked the response against the request after the
fact. Narrate: governance work doesn't stop just because the response was
already sent.

## Shot 6 — Console tour

- **Dashboard**: aggregate request/block counts, findings by category, a
  24-hour timeline. Point out the numbers include everything from the
  scenarios just run.
- **Workloads**: the policy profile that governed all of the above
  (`balanced`, the seeded default) — mention this is where budgets and fail
  mode live, and where a real deployment would register more than one
  workload for different applications or environments.
- **Session Drilldown**: open the hallucination session from Shot 5 — its
  finding is a real row, so this page shows exactly what proved it (category,
  confidence, evaluator tier). If you also open the escalated session from
  Shot 4, be precise on camera: you'll see turn 1's violation and the
  session's current risk/strikes, but *not* a row for turn 2's escalation
  block itself — that block had no content of its own to log, which is
  exactly the console gap the README calls out under Known limitations.
  Don't imply the drilldown shows the escalation block happening; it shows
  the ledger state that caused it.
- **Live Feed**: if possible, send one more request while this page is open
  on screen so a new row visibly appears — the most convincing 5 seconds of
  the whole video for showing this is a live system, not a slideshow.

## Closing (10-15s)

One line on scope, matching the README's own Known limitations: this is a
buffered (non-streaming) hackathon build, self-checked end to end against a
real Postgres, Redis, and model API rather than a mocked test suite. Don't
overclaim past what was actually shown.
