import { NavLink, Route, Routes } from 'react-router-dom'
import { Dashboard } from './Dashboard'
import { DetectionHealth } from './DetectionHealth'
import { LiveFeed } from './LiveFeed'
import { Playground } from './Playground'
import { ReviewQueue } from './ReviewQueue'
import { SessionDetail } from './SessionDetail'
import { Sessions } from './Sessions'
import { Workloads } from './Workloads'

function navLinkClass({ isActive }: { isActive: boolean }) {
  return `rounded-sm px-3 py-1.5 text-sm font-medium transition-colors duration-[var(--duration-base)] ${
    isActive
      ? 'bg-[var(--color-surface)] text-[var(--color-ink)]'
      : 'text-[var(--color-muted)] hover:text-[var(--color-ink)]'
  }`
}

function App() {
  return (
    <div className="min-h-screen bg-[var(--color-canvas)]">
      <header className="border-b border-[var(--color-border)]">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-4">
          <p className="text-sm font-medium text-[var(--color-accent)]">ControlPlane</p>
          <nav className="flex items-center gap-1" aria-label="Primary">
            <NavLink to="/" end className={navLinkClass}>
              Dashboard
            </NavLink>
            <NavLink to="/workloads" className={navLinkClass}>
              Workloads
            </NavLink>
            <NavLink to="/sessions" className={navLinkClass}>
              Sessions
            </NavLink>
            <NavLink to="/review" className={navLinkClass}>
              Review
            </NavLink>
            <NavLink to="/detection-health" className={navLinkClass}>
              Detection Health
            </NavLink>
            <NavLink to="/feed" className={navLinkClass}>
              Live Feed
            </NavLink>
            <NavLink to="/playground" className={navLinkClass}>
              Playground
            </NavLink>
          </nav>
        </div>
      </header>

      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/workloads" element={<Workloads />} />
        <Route path="/sessions" element={<Sessions />} />
        <Route path="/sessions/:sessionId" element={<SessionDetail />} />
        <Route path="/review" element={<ReviewQueue />} />
        <Route path="/detection-health" element={<DetectionHealth />} />
        <Route path="/feed" element={<LiveFeed />} />
        <Route path="/playground" element={<Playground />} />
      </Routes>

      <footer className="mx-auto max-w-6xl px-6 py-6 text-xs text-[var(--color-muted)]">
        ControlPlane.ai · AI governance proxy console.
      </footer>
    </div>
  )
}

export default App
