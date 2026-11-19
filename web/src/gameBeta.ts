// Game-by-game chances (beta): helpers shared by the player page, My Roster and How it works.
import type { GameBeta, UpcomingGame } from './types'

/** "92%"; under 5% is shown as "<5%" so near-zero overrides don't read as exact. */
export function chance(p: number): string {
  return p < 0.05 ? '<5%' : `${Math.round(p * 100)}%`
}

/** Games from the asOf date through the end of the fantasy week. */
export function thisWeek(games: UpcomingGame[], weekEnd: string): UpcomingGame[] {
  return games.filter((g) => g.date <= weekEnd)
}

export interface WeekLine {
  id: number
  games: number
  expected: number
}

/** Each player's games this week and the expected number played (sum of chances); players without chances are left out. */
export function weekLines(ids: number[], beta: GameBeta): WeekLine[] {
  const out: WeekLine[] = []
  for (const id of ids) {
    const games = beta.players[String(id)]
    if (!games) continue
    const week = thisWeek(games, beta.weekEnd)
    out.push({ id, games: week.length, expected: week.reduce((s, g) => s + g.p, 0) })
  }
  return out
}

/** Why a game's chance comes from the injury status rather than the model. */
export function overrideText(g: UpcomingGame): string | null {
  if (g.override === 'injury report') return 'Out on the injury report'
  if (g.override === 'return date') return 'Before the expected return'
  return null
}
