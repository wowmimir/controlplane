// Recharts renders SVG props as literal attributes, not CSS, so chart
// colors can't reference the CSS custom properties in index.css directly.
// Keep these in sync with index.css's @theme block by hand - this file
// exists only because Recharts needs literal values.
export const chartColors = {
  accent: '#38bdf8',
  border: '#24303d',
  muted: '#94a3b8',
  ink: '#f1f5f9',
  surface: '#121821',
} as const
