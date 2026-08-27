# Business Proposal Outline — ControlPlane.ai

**Purpose of this file**: this is a briefing for whoever writes the proposal, not the proposal
itself. It's the vision/direction; you decide the framing, narrative, and design. Treat
`.agents/STATUS.md`, `.agents/forks.md`, and `.agents/decisions.md` as the source of truth for
anything technical — if this file and those disagree, they win (this file may lag behind the code).

**Deliverable target**: PDF, 20MB. Problem framing, solution design, target users, business case
and impact, a phased roadmap, key risks with mitigations.

## Grounding rules — read this before writing anything

The biggest risk to this proposal is overclaiming — describing ControlPlane as a finished SaaS
product when it's a working prototype. Judges can and will ask "can I sign up right now?" Don't put
us in a position where the honest answer contradicts the deck.

- **Real and demoable today**: the governance proxy itself (request/response scanning across 6
  categories, 3 evaluator tiers, the session risk ledger with decay/strikes/escalation, the audit
  trail, the console) — *plus* everything from the Round 2 work (`.agents/STATUS.md` Phases 8 and
  10): policy that varies behavior by use case, a block / redact / flag-for-review tiered response,
  a human feedback loop with a live per-pattern false-positive rate, per-workload category
  overrides, three simulated concurrent use cases, a measured governance-overhead stat, and a
  browser prompt playground. This is the actual proof-of-concept — lead with it. Verify any
  specific claim against `.agents/STATUS.md` before writing it as done.
- **Explicitly NOT built, and not being built before the deadline** (see `.agents/forks.md` Fork
  #5): user signup, API keys, a hosted public product, real multi-provider model routing, real
  retrieval-verification (RAG), streaming. **Do not describe these in present tense.** They belong
  in the Phased Roadmap as future work, described with reasoning for why they're next, not
  presented as already solved.
- If in doubt about whether something is real, ask — don't infer from how confident the code's own
  comments sound (this codebase documents itself in a lot of detail, but detail isn't the same as
  "shipped and enforced").

---

## 1. Problem Framing

Ground this in the hackathon's own framing, don't reinvent it: enterprises now run generative AI
across many simultaneous use cases — customer-facing chatbots, internal copilots, decision-support
tools in regulated workflows — and each carries a different risk profile depending on the model,
the data behind it, and how its output gets used downstream. Most organizations have no consistent
layer watching what goes in and out of these systems, and the tools that exist mostly check one
message at a time — they don't catch a pattern of bad behavior building up across a conversation,
and they don't leave a defensible record of *why* something was allowed or blocked.

Points to hit:
- The cost of getting this wrong isn't hypothetical — a leaked customer detail, a jailbroken support
  bot, a hallucinated decision-support answer in a regulated workflow are all reputational/legal
  exposure, not edge cases.
- Point-in-time content filters (profanity lists, single-message classifiers) don't address
  *behavioral* risk — a user probing across several turns, or an agent whose earlier bad output
  shapes its own next action.
- Teams either build this themselves (slow, and every team reinvents the same PII regexes) or ship
  without it (risk accepted silently).

## 2. Solution Design

What ControlPlane actually is: a governance proxy that sits between an application and its model
API, using the same request shape the app already speaks (OpenAI's `/v1/chat/completions`), so
adopting it is a base-URL change, not a rewrite. It scans both directions, tiers its checks by cost
(instant pattern-matching → an async AI-as-judge, so you're not paying model-inference cost on every
message), and — the actual differentiator — tracks a decaying risk score *per conversation*, so a
pattern of concerning behavior gets caught even when no single message crosses the line alone.

**Use this table directly — it maps the hackathon's own stated complexities to what the system
already does. This is probably the strongest section of the whole proposal, because it's not a
claim, it's a description of working code:**

| Rubric's stated complexity | How ControlPlane answers it today |
|---|---|
| "A single one-size-fits-all checking approach rarely works" | Per-app policy container (`Workload`): the profile (`strict` / `balanced` / `fast`) sets the escalation thresholds *and* picks the response action — hard-block, redact-and-release, or flag-for-review — so risk tolerance genuinely varies by use case. (Latency/cost budgets are still recorded-only.) |
| "Bias, hallucination, and privacy risks often overlap" | Independent single-purpose evaluators per category, but one incident can produce multiple findings across categories simultaneously — no forced single-label classification |
| "No reliable real-time ground truth... makes automated verification difficult" | Discovered firsthand during testing: the model refuses to fabricate on request, and the AI-judge correctly recognized a truthful correction as *not* a hallucination — cite this as evidence we've actually grappled with the problem, not guessed at it |
| "Over-flagging creates alert fatigue; under-flagging creates liability" | Four outcomes now exist — pass, flag-for-review, redact-and-release, hard-block — chosen by the workload's profile, so this tradeoff is tunable per use case instead of all-or-nothing. A human confirm/reject loop feeds a live false-positive rate per detection pattern |
| "Multi-turn conversations... introduce compounding risk" | The core mechanism: a per-session risk ledger that decays on clean turns and escalates on a pattern, blocking a *future* clean message purely on accumulated history |
| "Regulatory expectations differ by geography/industry... rigid rules age quickly" | Policy is scoped per registered app (workload), carries geography/industry tags, and per-category overrides (disable a check, raise a confidence floor, mute a pattern) let one workload evaluate content differently from another — the demo set includes an EU / GDPR-tagged `strict` workload. Driving more of the policy automatically from the tags is the near-term step |
| "Enterprises consume a model via API... limiting how deeply a checker can inspect internals" | The whole design was input/output-only from day one — never assumes access to model weights or internals |

Architecture, in one sentence for the proposal: **pre-response gate (blocks before the model is
even called) + inline response check (blocks before the reply reaches the caller) + async post-hoc
audit (an AI judge that checks after release, for issues too slow to catch synchronously)** — call
out that most competing tools only implement one of these three placements.

## 3. Target Users

Suggested personas — flesh out, don't feel bound to exactly these three:
- **Platform/infra engineering lead** at a company shipping an AI feature — the implementer, cares
  about drop-in integration and not adding meaningful latency.
- **Compliance/risk officer** in a regulated industry (fintech, healthcare, legal) — the economic
  buyer, cares about the audit trail and defensibility ("why was this blocked" needs a real answer).
- **AI product manager** — the day-to-day console user, cares about not drowning in false-positive
  noise (this is the flag-vs-block tuning story).

## 4. Business Case and Impact

- Reframe as risk reduction + build-time savings, not just "a feature." The alternative to buying
  this is building it in-house (this hackathon build is a rough proxy for what that costs) or
  shipping without it (silent risk acceptance).
- Pricing shape: usage-based (per request/per 1k interactions) for self-serve, or enterprise
  licensing for regulated/self-hosted customers who need control over where data goes.
- Reference Parameters from the brief (tens of thousands of interactions/week across several
  concurrent use cases) are a reasonable basis for an illustrative cost/impact model — state
  whatever assumptions you use explicitly, the brief invites this ("you're encouraged to make your
  own reasonable assumptions, state them clearly").
- Competitive framing: most existing AI-guardrail tools evaluate one message in isolation; the
  session-level memory and full audit trail are the real differentiators, not the individual
  detectors (regex PII/jailbreak detection alone is commoditized).

## 5. Phased Roadmap

Reuse this structure directly — it's already locked in the code's own planning docs, so it can't
drift out of sync with what's actually built:

- **Phase 1 (built, demoable now)** — the core proxy: 6-category taxonomy, 3 evaluator tiers, the
  session risk ledger (decay/strikes/escalation), full audit trail, and the operator console
  (dashboard, workload management, sessions + drilldown, live feed).
- **Phase 2 (built — `.agents/STATUS.md` Phases 8 and 10)** — policy that actually varies behavior
  by use case (per-profile escalation thresholds plus a block / redact-and-release / flag-for-review
  action split), a human feedback loop with a live per-pattern false-positive rate (the Review and
  Detection Health console pages), per-workload category overrides, three simulated concurrent use
  cases run against a labelled corpus for a real recall figure, a measured `governance_overhead_ms`
  stat, and a browser prompt playground for typing test traffic live.
- **Phase 3 (near-term, not started)** — real embedding/statistical detection for the currently-stub
  middle tier, retrieval-grounded verification against real source documents (today's AI-judge only
  checks internal consistency, not real-world facts; a deliberately *simulated* RAG check was
  scoped as optional and skipped), agent/tool-call-aware risk tracking for systems that take
  actions, not just generate text.
- **Phase 4 (product maturity, not started)** — real authentication and multi-tenancy, self-serve
  signup and API key issuance, a hosted deployment, multi-provider model routing, streaming support.
  Be honest here: this phase is what turns a working mechanism into an actual product a stranger
  could sign up for — currently everything is single-tenant with no auth, by deliberate scope choice
  for this round, not an oversight.

## 6. Key Risks and Mitigations

- **False positives / false negatives from pattern-based detection** — mitigated by the tiered
  fallback (cheap → medium → AI-judge) and a feedback loop that measures and surfaces the actual
  false-positive rate *per detection pattern* (the Review and Detection Health pages), instead of
  assuming detection is perfect. False-negative rate on open traffic stays structurally
  unmeasurable without independent ground truth — the labelled-corpus recall figure from the
  multi-use-case sim is the honest proxy, and the proposal should say so.
- **Added latency from a governance layer** — the synchronous checks are single-digit-millisecond
  regex/keyword scans by design; the AI-judge tier runs asynchronously *after* the response is
  already released, so it adds zero latency to what the user experiences. This is now measured, not
  asserted: every full-pipeline turn records `governance_overhead_ms` (wall-clock time of the
  interception code, excluding the model call), surfaced as a p50/p95 pair on the Dashboard — cite
  those numbers directly.
- **Async-judge throughput at scale** — the background AI-judge check runs in-process (no job queue
  yet, by deliberate MVP scope — see `forks.md` Fork #5), and individual judge calls have been
  observed taking up to ~11-12 seconds. At the brief's "tens of thousands of interactions/week"
  scale this is a throughput/backpressure question, not a per-request latency one — name it as
  "known, and a durable job queue is the stated next step" rather than leaving it for a judge to
  spot unprompted.
- **Data source governance quality varies** — the brief's own Reference Parameters assume "a mix of
  well-governed and loosely governed internal data sources." Frame this as a per-workload risk input
  rather than something the checker can fully compensate for: a workload known to draw on loosely
  governed data should be configurable toward a stricter profile/tighter thresholds — the same
  `Workload.metadata`-based mechanism already used for geography/industry tags is the natural
  extension point.
- **Competitive risk from existing guardrail vendors** — differentiate on session-level behavioral
  memory and audit-trail defensibility, not on having "a PII detector" (table stakes).
- **Integration friction** — mitigated by the drop-in, OpenAI-compatible API shape; adopting this is
  a base-URL change for any app already using an OpenAI-shaped client.
- **Current-build limitations that are real and worth naming rather than hiding** — no
  authentication on the proxy today (anyone who can reach it can assert any session/app identity),
  no production deployment yet. Framing these as "known, scoped, and next on the roadmap" is
  stronger than pretending they don't exist — judges will find the gaps either way.

## 7. Suggested visuals (20MB budget is generous, use it)

- A real screenshot of the Session Drilldown page showing an actual hallucination finding (category,
  confidence, evaluator tier) — this is proof, not a mockup.
- A simple architecture diagram: App → ControlPlane → Model API, with the three evaluator tiers and
  the risk ledger as a side component.
- The rubric-complexity mapping table from Section 2 above, reformatted visually — it's a strong,
  skimmable slide/page on its own.
