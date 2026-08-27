import { useState } from 'react'
import { patchFindingReview } from '../api'
import type { ReviewStatus } from '../types'

// 8.3: the Confirm / Mark-false-positive controls on a finding. Used both on
// a finding row in Session Drilldown and on every row of the Review queue.
// An unreviewed finding shows both actions; a reviewed one shows its status
// with an "Undo" back to unreviewed and the option to switch to the other
// verdict. The PATCH happens here; the parent is told the new status via
// onReviewed so its own list/row updates without a full reload.

const STATUS_LABEL: Record<ReviewStatus, string> = {
  unreviewed: 'Unreviewed',
  confirmed: 'Confirmed',
  false_positive: 'False positive',
}

// Full literal class strings per state so Tailwind's static scanner finds
// them, matching DispositionBadge's pattern.
const STATUS_CLASS: Record<ReviewStatus, string> = {
  unreviewed: 'border-[var(--color-border)] text-[var(--color-muted)]',
  confirmed: 'border-[var(--color-success)]/40 text-[var(--color-success)]',
  false_positive: 'border-[var(--color-warning)]/40 text-[var(--color-warning)]',
}

const buttonClass =
  'rounded-sm border border-[var(--color-border)] px-2 py-0.5 text-xs text-[var(--color-body)] transition-colors duration-[var(--duration-base)] hover:border-[var(--color-accent)] hover:text-[var(--color-ink)] disabled:opacity-50'

export function ReviewStatusBadge({ status }: { status: ReviewStatus }) {
  return (
    <span
      className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-medium ${STATUS_CLASS[status]}`}
    >
      {STATUS_LABEL[status]}
    </span>
  )
}

interface ReviewControlsProps {
  findingId: string
  reviewStatus: ReviewStatus
  onReviewed: (status: ReviewStatus) => void
}

export function ReviewControls({ findingId, reviewStatus, onReviewed }: ReviewControlsProps) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function set(next: ReviewStatus) {
    if (next === reviewStatus || pending) return
    setPending(true)
    setError(null)
    try {
      const updated = await patchFindingReview(findingId, next)
      onReviewed(updated.review_status)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save.')
    } finally {
      setPending(false)
    }
  }

  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <ReviewStatusBadge status={reviewStatus} />
      {reviewStatus === 'unreviewed' ? (
        <>
          <button type="button" className={buttonClass} disabled={pending} onClick={() => set('confirmed')}>
            Confirm
          </button>
          <button
            type="button"
            className={buttonClass}
            disabled={pending}
            onClick={() => set('false_positive')}
          >
            False positive
          </button>
        </>
      ) : (
        <>
          <button
            type="button"
            className={buttonClass}
            disabled={pending}
            onClick={() => set(reviewStatus === 'confirmed' ? 'false_positive' : 'confirmed')}
          >
            {reviewStatus === 'confirmed' ? 'Change to false positive' : 'Change to confirmed'}
          </button>
          <button type="button" className={buttonClass} disabled={pending} onClick={() => set('unreviewed')}>
            Undo
          </button>
        </>
      )}
      {error ? <span className="text-xs text-[var(--color-error)]">{error}</span> : null}
    </span>
  )
}
