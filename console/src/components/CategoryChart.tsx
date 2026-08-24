import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { chartColors } from '../theme'
import type { CategoryCount } from '../types'

interface CategoryChartProps {
  data: CategoryCount[]
}

const CATEGORY_LABELS: Record<string, string> = {
  pii: 'PII',
  hallucination: 'Hallucination',
  toxicity: 'Toxicity',
  bias: 'Bias',
  prompt_injection: 'Prompt injection',
  custom_policy: 'Custom policy',
}

export function CategoryChart({ data }: CategoryChartProps) {
  const chartData = data.map((row) => ({
    ...row,
    label: CATEGORY_LABELS[row.category] ?? row.category,
  }))

  return (
    <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
      <h2 className="text-lg font-medium text-[var(--color-ink)]">Findings by category</h2>
      <p className="mt-1 text-sm text-[var(--color-muted)]">
        All-time count of every Finding recorded, across every evaluator tier.
      </p>
      {data.length === 0 ? (
        <p className="mt-8 py-8 text-center text-sm text-[var(--color-muted)]">
          No findings recorded yet.
        </p>
      ) : (
        <>
          <div className="mt-4 h-64" aria-hidden="true">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={chartColors.border} vertical={false} />
                <XAxis
                  dataKey="label"
                  stroke={chartColors.muted}
                  tick={{ fill: chartColors.muted, fontSize: 12 }}
                  tickLine={false}
                  axisLine={{ stroke: chartColors.border }}
                />
                <YAxis
                  allowDecimals={false}
                  stroke={chartColors.muted}
                  tick={{ fill: chartColors.muted, fontSize: 12 }}
                  tickLine={false}
                  axisLine={false}
                  width={32}
                />
                <Tooltip
                  cursor={{ fill: chartColors.border, opacity: 0.4 }}
                  contentStyle={{
                    background: chartColors.surface,
                    border: `1px solid ${chartColors.border}`,
                    borderRadius: 8,
                    color: chartColors.ink,
                  }}
                  labelStyle={{ color: chartColors.ink }}
                />
                <Bar dataKey="count" fill={chartColors.accent} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          {/* Text fallback so the data isn't chart-shape-only for assistive tech. */}
          <table className="sr-only">
            <caption>Findings by category</caption>
            <thead>
              <tr>
                <th scope="col">Category</th>
                <th scope="col">Count</th>
              </tr>
            </thead>
            <tbody>
              {chartData.map((row) => (
                <tr key={row.category}>
                  <td>{row.label}</td>
                  <td>{row.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  )
}
