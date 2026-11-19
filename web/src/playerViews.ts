// The All players page's views: everyone, who's injured, and who's worth stashing.
// The view and team live in the URL (/?view=injured&team=LAL) so they can be linked.
import { fantasyValue, isInjured } from './data.ts'
import type { FantasyFormat, FantasyPlayer, PlayerSummary } from './types'

export type PlayerView = 'all' | 'injured' | 'stash'

export const VIEWS: { id: PlayerView; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'injured', label: 'Injured' },
  { id: 'stash', label: 'Worth stashing' },
]

/** The view named in the URL; anything else is the full list. */
export function parseView(raw: string | null): PlayerView {
  return raw === 'injured' || raw === 'stash' ? raw : 'all'
}

/** Everyone (or one team), highest expected games first: the updated forecast once the season is on. */
export function allPlayers(players: PlayerSummary[], team: string, seasonStarted: boolean): PlayerSummary[] {
  const key = (p: PlayerSummary) => (seasonStarted ? (p.updated ?? -1) : p.shown)
  return players.filter((p) => !team || p.team === team).sort((a, b) => key(b) - key(a))
}

/** Players out with an injury (or with a known return timeline), best-known first. */
export function injuredPlayers(players: PlayerSummary[], team: string): PlayerSummary[] {
  return players.filter((p) => isInjured(p) && (!team || p.team === team)).sort((a, b) => b.recentMinutes - a.recentMinutes)
}

export interface StashRow {
  p: FantasyPlayer
  /** Rest-of-season value above replacement, counting only games after the return. */
  value: number
}

/**
 * Players out now (injured, or missing games without a report) who are still worth a
 * roster spot: positive rest-of-season value, highest first. Rookies are left out.
 */
export function stashPlayers(players: FantasyPlayer[], format: FantasyFormat, replacement: number, team: string): StashRow[] {
  return players
    .filter((p) => p.out && !p.rookie && (!team || p.team === team))
    .map((p) => ({ p, value: fantasyValue(p.perGame[format], replacement, p.restGames) }))
    .filter((r) => r.value > 0)
    .sort((a, b) => b.value - a.value)
}
