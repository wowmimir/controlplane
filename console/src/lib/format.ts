// Shared id/name display helper. Extracted from Workloads.tsx (5.2) so
// Sessions.tsx/SessionDetail.tsx (5.3) use the same implementation instead
// of a second inline copy.
export function displayId(id: string, name?: string | null): string {
  if (name) return name
  return `${id.slice(0, 8)}…`
}
