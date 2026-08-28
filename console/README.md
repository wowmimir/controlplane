# ControlPlane console

The operator console for ControlPlane. It reads the backend's `/api/console/*`
endpoints and the OpenAI-shaped `/v1/chat/completions` endpoint directly from
the browser; it has no server of its own.

**Stack:** React 19 + TypeScript + Vite, Tailwind v4 (dark only, by design;
see `src/index.css`), React Router. Lint via Oxlint.

## Run it

```bash
npm install
cp .env.example .env        # sets VITE_API_BASE_URL; defaults to http://localhost:8000 if absent
npm run dev                 # http://localhost:5173
```

The backend must be running (default `http://localhost:8000`) and CORS there
allows the `5173` origin. Populate it with real traffic first:
`uv run python scripts/seed_demo.py` from the repo root.

```bash
npm run build   # tsc -b && vite build
npm run lint    # oxlint
```

## Pages

Dashboard, Workloads, Sessions (+ per-session drilldown), Review, Detection
Health, Live Feed, Playground. Routes and nav live in `src/App.tsx`; API calls
in `src/api.ts`; backend-mirrored types in `src/types.ts`.
