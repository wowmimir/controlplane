interface StatTileProps {
  label: string
  value: number
  accent?: boolean
  caveat?: string
}

export function StatTile({ label, value, accent = false, caveat }: StatTileProps) {
  return (
    <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
      <dl>
        <dt className="text-sm text-[var(--color-muted)]">{label}</dt>
        <dd
          className={`mt-2 text-3xl font-bold tabular-nums ${
            accent ? 'text-[var(--color-accent)]' : 'text-[var(--color-ink)]'
          }`}
        >
          {value.toLocaleString()}
        </dd>
      </dl>
      {caveat ? <p className="mt-3 text-sm text-[var(--color-muted)]">{caveat}</p> : null}
    </div>
  )
}
