// Is the site's data going stale? The refresh has two halves: the Mac downloads the NBA
// stats (rostersAsOf is when) and GitHub Actions rebuilds the site (generatedAt). If
// either is more than two days old, the site says so next to the "games thru" date.
import type { Meta } from './types.ts'

export const STALE_AFTER_HOURS = 48

/** A timestamp from the export: an ISO string, with or without a time zone. */
function parse(iso: string | null | undefined): Date | null {
  if (!iso) return null
  // Times without a zone (the Mac's stats download) can carry microseconds; keep whole seconds.
  const hasZone = /(Z|[+-]\d\d:\d\d)$/.test(iso)
  const date = new Date(hasZone ? iso : iso.slice(0, 19))
  return Number.isNaN(date.getTime()) ? null : date
}

/** When the data was last refreshed, if that's more than two days ago; otherwise null. */
export function staleSince(meta: Pick<Meta, 'rostersAsOf' | 'generatedAt'>, now = new Date()): Date | null {
  const times = [parse(meta.rostersAsOf), parse(meta.generatedAt)].filter((d): d is Date => d !== null)
  if (!times.length) return null
  const oldest = new Date(Math.min(...times.map((d) => d.getTime())))
  return now.getTime() - oldest.getTime() > STALE_AFTER_HOURS * 3600 * 1000 ? oldest : null
}

/** "Nov 17" */
export function staleDate(date: Date): string {
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}
