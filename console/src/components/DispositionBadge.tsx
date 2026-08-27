import type { Disposition } from '../types'

// 8.2: replaces the old two-state BlockedBadge (previously duplicated
// identically in LiveFeed.tsx and SessionDetail.tsx) with a shared,
// three-state badge - a fast-profile cheap-tier hit now releases as 200
// with disposition=flagged instead of hard-blocking, so "blocked" and
// "not blocked" are no longer the only two outcomes worth showing.
//
// Full literal class strings per state (not composed from a variable) so
// Tailwind's static scanner can find them - matches this codebase's
// existing ternary-based badge pattern.
// 8.5: `redacted` is the fourth state - a balanced-profile response-side
// pii/custom_policy hit where the span was blanked and the edited response
// released as 200. Its own violet token (--color-info), distinct from the
// three status colors.
const LABELS: Record<Disposition, string> = {
  clean: 'Clean',
  flagged: 'Flagged',
  blocked: 'Blocked',
  redacted: 'Redacted',
}

const CLASSES: Record<Disposition, string> = {
  clean: 'border-[var(--color-success)]/40 text-[var(--color-success)]',
  flagged: 'border-[var(--color-warning)]/40 text-[var(--color-warning)]',
  blocked: 'border-[var(--color-error)]/40 text-[var(--color-error)]',
  redacted: 'border-[var(--color-info)]/40 text-[var(--color-info)]',
}

export function DispositionBadge({ disposition }: { disposition: Disposition }) {
  return (
    <span
      className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-medium ${CLASSES[disposition]}`}
    >
      {LABELS[disposition]}
    </span>
  )
}
