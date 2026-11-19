// The saved roster lives in this browser only. Storage can be blocked or empty
// (private windows, cleared site data), so every read and write is guarded.
import { MAX_ROSTER } from './model.ts'

const KEY = 'next82.myRoster.v1'

export interface Saved {
  ids: number[]
  /** Seed for the season simulation, so the same roster gives the same numbers. */
  seed: number
}

export const DEFAULT_SEED = 82

/** Parse what was stored, dropping anything malformed. */
export function parseSaved(raw: string | null): Saved {
  const empty = { ids: [], seed: DEFAULT_SEED }
  if (!raw) return empty
  try {
    const data = JSON.parse(raw)
    const ids = Array.isArray(data?.ids) ? data.ids.filter((id: unknown) => Number.isInteger(id) && (id as number) > 0) : []
    const seed = Number.isInteger(data?.seed) ? data.seed : DEFAULT_SEED
    return { ids: [...new Set<number>(ids)].slice(0, MAX_ROSTER), seed }
  } catch {
    return empty
  }
}

export function loadSaved(): Saved {
  try {
    return parseSaved(window.localStorage.getItem(KEY))
  } catch {
    return parseSaved(null)
  }
}

export function save(saved: Saved): void {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(saved))
  } catch {
    // Storage unavailable: the roster still works for this visit.
  }
}
