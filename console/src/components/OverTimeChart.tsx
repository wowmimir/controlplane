import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { chartColors } from '../theme'
import type { TimeBucket } from '../types'

interface OverTimeChartProps {
  data: TimeBucket[]
}

function formatHour(bucket: string): string {
  return new Date(bucket).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
  })
}

export function OverTimeChart({ data }: OverTimeChartProps) {
  const chartData = data.map((row) => ({ ...row, label: formatHour(row.bucket) }))

  return (
    <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
      <h2 className="text-lg font-medium text-[var(--color-ink)]">Requests over time</h2>
      <p className="mt-1 text-sm text-[var(--color-muted)]">Last 24 hours, grouped by hour.</p>
      {data.length === 0 ? (
        <p className="mt-8 py-8 text-center text-sm text-[var(--color-muted)]">
          No requests in the last 24 hours.
        </p>
      ) : (
        <>
          <div className="mt-4 h-64" aria-hidden="true">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke={chartColors.border} vertical={false} />
                <XAxis
                  dataKey="label"
                  stroke={chartColors.muted}
                  tick={{ fill: chartColors.muted, fontSize: 12 }}
                  tickLine={false}
                  axisLine={{ stroke: chartColors.border }}
                  minTickGap={24}
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
                  contentStyle={{
                    background: chartColors.surface,
                    border: `1px solid ${chartColors.border}`,
                    borderRadius: 8,
                    color: chartColors.ink,
                  }}
                  labelStyle={{ color: chartColors.ink }}
                />
                <Legend wrapperStyle={{ color: chartColors.muted, fontSize: 12 }} />
                <Line
                  type="monotone"
                  dataKey="total"
                  name="Total requests"
                  stroke={chartColors.muted}
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="blocked"
                  name="Blocked"
                  stroke={chartColors.accent}
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <table className="sr-only">
            <caption>Requests over time, last 24 hours by hour</caption>
            <thead>
              <tr>
                <th scope="col">Hour</th>
                <th scope="col">Total</th>
                <th scope="col">Blocked</th>
              </tr>
            </thead>
            <tbody>
              {chartData.map((row) => (
                <tr key={row.bucket}>
                  <td>{row.label}</td>
                  <td>{row.total}</td>
                  <td>{row.blocked}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  )
}
