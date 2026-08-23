# AGENTS.md — ControlPlane.ai (Hackathon Build)

## 1. Identity & Golden Rule
You are a senior engineer building a hackathon MVP.
**Rule:** Never write code without a spec in `prompts/`. Never mark a feature done without updating `STATUS.md`.

## 2. The Immutable Context (Load Order)
For every task, load these files in this order:
1. **`STATUS.md`** — The progress tracker. ALWAYS read this first.
2. **`forks.md`** — The locked implementation decisions. Read this SECOND so you stay inside the boundaries.
3. **`decisions.md`** — The memory bank. Read this THIRD before asking me any question.
4. **`plan.md`** — The constitution. Read ONLY for deep architecture questions (rarely needed).

## 3. The Tech Stack (Locked — from forks.md)
- **API/Proxy**: Python (FastAPI) — Async-native.
- **Session Ledger**: Redis (TTL 15min).
- **Audit Store**: PostgreSQL (Workload → Session → Execution → Finding).
- **Async Tasks**: FastAPI `BackgroundTasks` (No Celery for MVP).
- **Frontend**: React (for the console dashboard).
- **API Shape**: OpenAI-compatible (`/v1/chat/completions`).
- **Evaluators**:
  - Cheap: Regex/PII detectors (synchronous, <5ms).
  - Medium: Embedding similarity (only when cheap is inconclusive).
  - Expensive: LLM-as-judge (async, runs post-response).

## 4. The Slim Workflow (Execute this loop)
For every feature:
1. **Read** `STATUS.md`, `forks.md`, and `decisions.md`.
2. **Architect**: Use `/architect` (or write manually) a detailed plan to `prompts/[feature]-plan.md`.
3. **Gate**: Ask me: *"Plan ready. Approve?"* → **WAIT** for my explicit "yes".
4. **Develop**: Build strictly from the spec.
5. **Self-Check**: Run `python -m pytest` (if tests exist) or manually verify the feature works.
6. **Update**: 
   - Mark complete in `STATUS.md`.
   - Log any non-obvious decisions/hacks to `decisions.md` (date, decision, rationale).
7. **Handoff**: State: *"Ready for next chat/feature."*

## 5. The Proxy Constraint
The proxy MUST support the **OpenAI API shape** (`/v1/chat/completions`) to prove plug-and-play. The proxy intercepts the request, runs checks, then forwards to the real OpenAI/Anthropic endpoint.

## 6. Security Hard Rule
Cheap-tier failures (PII, prompt injection) **MUST** block the response before it reaches the user. Never expose API keys to the frontend.

## 7. Logging to decisions.md
Whenever you make a choice that:
- Has two or more viable options,
- Is not explicitly stated in `plan.md` or `forks.md`,
- Would be annoying to re-litigate in a future session,

Log it immediately to `decisions.md` with this format:

| Date | Decision | Rationale |
| :--- | :--- | :--- |
| YYYY-MM-DD | What you chose | Why you chose it |

**Do not ask me for permission to log a decision.** Just log it and keep moving.

## 8. What to Skip (Hackathon Speed)
- **DO NOT** write automated test suites (we skip `test`).
- **DO NOT** write pull request bodies or changelogs (we skip `document`).
- **DO NOT** run a full `sync` reconciliation. Just update `STATUS.md` and `decisions.md`.

## 9. When Stuck (The "Assumed" Spec Rule)
If you hit a load-bearing decision not covered in any file:
1. Propose the simplest, easiest-to-reverse path.
2. Write it into the spec as an `Assumed` decision.
3. Ask me to ratify it (or log it to `decisions.md`).
4. **Do not** let it block the build.

## 10. Skills Available
You have the JSMasteryPro skills installed. Use them:
- `/architect` — To generate a spec.
- `/review` — To check work before marking done.
- `/recover` — When something breaks and one fix didn't work.
- `/remember save` — At the end of a session.
- `/remember restore` — At the start of a new session.