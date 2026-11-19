// Safer players to swap in for a high-risk one: the nearest neighbours on per-game
// production among players who share a position and have a safer availability forecast.
import { isInjured } from '../data.ts'
import type { Tier } from '../types'
import type { RosterPlayer } from './model.ts'

/** Per-game stats compared (fantasy.json's blend of this season with the last three). */
export const SWAP_STATS = ['MIN', 'PTS', 'REB', 'AST', 'STL', 'BLK', 'FG3M', 'TOV'] as const
export const SWAP_COUNT = 3

const TIER_RANK: Record<Tier, number> = { Risky: 0, Moderate: 1, Safe: 2 }

/** Positions share a letter ('G-F' and 'F-C' share F). A missing position matches anything. */
export function positionsOverlap(a: string | null, b: string | null): boolean {
  if (!a || !b) return true
  const letters = new Set(a.split('-'))
  return b.split('-').some((l) => letters.has(l))
}

/** Safer than `p`: a better tier, more games expected from here on, and not injured right now. */
export function isSafer(candidate: RosterPlayer, p: RosterPlayer): boolean {
  if (!candidate.tier || isInjured(candidate)) return false
  const rank = p.tier ? TIER_RANK[p.tier] : -1
  return TIER_RANK[candidate.tier] > rank && candidate.rest > p.rest
}

/** Mean and spread of each stat across the pool, so every stat counts the same. */
function scales(pool: RosterPlayer[]): Record<string, { mean: number; sd: number }> {
  const out: Record<string, { mean: number; sd: number }> = {}
  for (const s of SWAP_STATS) {
    const values = pool.map((p) => p.stats?.[s]).filter((v): v is number => typeof v === 'number')
    const mean = values.reduce((a, b) => a + b, 0) / Math.max(values.length, 1)
    const variance = values.reduce((a, b) => a + (b - mean) ** 2, 0) / Math.max(values.length, 1)
    out[s] = { mean, sd: Math.sqrt(variance) || 1 }
  }
  return out
}

export interface Swap {
  player: RosterPlayer
  /** Distance in production (standardized stats); smaller is more similar. */
  distance: number
}

/**
 * Up to SWAP_COUNT safer players most like `p` per game, nearest first. Players in
 * `exclude` (the roster) are skipped. Empty if `p` has no per-game stats.
 */
export function swapSuggestions(p: RosterPlayer, pool: RosterPlayer[], exclude: Set<number>, count = SWAP_COUNT): Swap[] {
  if (!p.stats) return []
  const scale = scales(pool)
  const z = (q: RosterPlayer, s: string) => ((q.stats?.[s] ?? scale[s].mean) - scale[s].mean) / scale[s].sd
  const swaps: Swap[] = []
  for (const c of pool) {
    if (c.id === p.id || exclude.has(c.id) || !c.stats || !positionsOverlap(p.position, c.position) || !isSafer(c, p)) continue
    const distance = Math.sqrt(SWAP_STATS.reduce((sum, s) => sum + (z(c, s) - z(p, s)) ** 2, 0))
    swaps.push({ player: c, distance })
  }
  return swaps.sort((a, b) => a.distance - b.distance).slice(0, count)
}
