// My Roster: one row per player the roster can hold, built from index.json (games
// forecasts) and fantasy.json (per-game production, and rookies, who are only there).
// No React or Vite imports here, so `node --test` can run the tests.
import type { Fantasy, FantasyFormat, FantasyPlayer, NoTierReason, OutInfo, Override, PlayerSummary, Tier } from '../types'

export const MAX_ROSTER = 13

export interface RosterPlayer {
  id: number
  name: string
  search: string
  team: string | null
  position: string | null
  /** Null for rookies (fantasy.json has no age). */
  age: number | null
  tier: Tier | null
  noTierReason: NoTierReason | null
  rookie: boolean
  override: Override | null
  out: OutInfo | null
  playedSoFar: number
  /** Team games left: the most rest-of-season games the player can play. */
  gamesLeft: number
  /** Updated forecast of games still to come, and its likely range (10th-90th percentile). */
  rest: number
  restLow: number | null
  restHigh: number | null
  /** Per-game production (blended with recent seasons) for value and swap suggestions; null if unranked. */
  perGame: Record<FantasyFormat, number> | null
  stats: Record<string, number | null> | null
  /** Minutes in the last season played, to rank search suggestions. */
  recentMinutes: number
}

/** Lowercase, accent-free text so "jokic" matches "Jokić" (same as data.plain). */
export function plain(text: string): string {
  return text.normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase()
}

/**
 * Everyone who can be added: players on a roster with an updated forecast, plus ranked
 * rookies. Production comes from fantasy.json when the player is ranked there.
 */
export function rosterPool(players: PlayerSummary[], fantasy: Fantasy | null): RosterPlayer[] {
  const ranked = new Map((fantasy?.players ?? []).map((f) => [f.id, f]))
  const pool: RosterPlayer[] = []
  for (const p of players) {
    if (!p.team || p.updatedRest === null || p.gamesLeft === null) continue
    const f = ranked.get(p.id)
    const played = p.playedSoFar ?? 0
    pool.push({
      id: p.id,
      name: p.name,
      search: p.search,
      team: p.team,
      position: p.position ?? f?.position ?? null,
      age: p.age,
      tier: p.tier,
      noTierReason: p.noTierReason,
      rookie: false,
      override: p.override,
      out: p.out,
      playedSoFar: played,
      gamesLeft: p.gamesLeft,
      rest: p.updatedRest,
      // Season-total ranges, less the games already played.
      restLow: p.updatedLow === null ? null : Math.max(0, p.updatedLow - played),
      restHigh: p.updatedHigh === null ? null : Math.min(p.gamesLeft, p.updatedHigh - played),
      perGame: f?.perGame ?? null,
      stats: f?.stats ?? null,
      recentMinutes: p.recentMinutes,
    })
  }
  const inPool = new Set(pool.map((p) => p.id))
  for (const f of fantasy?.players ?? []) if (f.rookie && !inPool.has(f.id)) pool.push(fromRookie(f))
  return pool
}

function fromRookie(f: FantasyPlayer): RosterPlayer {
  return {
    id: f.id,
    name: f.name,
    search: plain(f.name),
    team: f.team,
    position: f.position ?? null,
    age: null,
    tier: null,
    noTierReason: 'rookie',
    rookie: true,
    override: f.override,
    out: f.out,
    playedSoFar: f.playedSoFar ?? 0,
    gamesLeft: f.gamesLeft,
    rest: f.restGames,
    restLow: f.restLow,
    restHigh: f.restHigh,
    perGame: f.perGame,
    stats: f.stats,
    // Rookies have no past minutes; rank them by this season's minutes.
    recentMinutes: (f.stats.MIN ?? 0) * (f.playedSoFar ?? 0),
  }
}

/** Players matching a search: word-start matches first, then anywhere; better-known players first. */
export function searchPool(pool: RosterPlayer[], query: string, exclude: Set<number>, limit = 8): RosterPlayer[] {
  const q = plain(query.trim())
  if (!q) return []
  const scored: [number, RosterPlayer][] = []
  for (const p of pool) {
    if (exclude.has(p.id)) continue
    const rank = p.search.startsWith(q) || p.search.split(' ').some((w) => w.startsWith(q)) ? 0 : p.search.includes(q) ? 1 : -1
    if (rank >= 0) scored.push([rank, p])
  }
  scored.sort((a, b) => a[0] - b[0] || b[1].recentMinutes - a[1].recentMinutes)
  return scored.slice(0, limit).map(([, p]) => p)
}

/** Rest-of-season fantasy value above replacement (same formula as data.fantasyValue); null if unranked. */
export function restValue(p: RosterPlayer, format: FantasyFormat, replacement: number): number | null {
  return p.perGame ? (p.perGame[format] - replacement) * p.rest : null
}
