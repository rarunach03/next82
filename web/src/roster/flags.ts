// Plain-English warnings about a roster's availability. Every rule and threshold is here.
import { isInjured } from '../data.ts'
import type { RosterPlayer } from './model.ts'

export const RULES = {
  /** "Top" players: the best this many per game. */
  topCount: 5,
  /** Warn when at least this many top players are high-risk. */
  riskyTopMin: 2,
  /** Warn when players this old or older are expected to supply... */
  olderAge: 33,
  /** ...at least this share of the roster's games left. */
  olderShareMin: 0.3,
  /** Warn when at least this many players are injured right now. */
  injuredMin: 2,
  /** Warn when at least this many players have no availability tier. */
  noTierMin: 3,
  /** Warn when a bad season (1 in 10) plays under this share of possible games. */
  badSeasonShareMax: 0.6,
} as const

/** High-risk: the Risky availability tier (a bad outcome is under 20 games). */
export function isHighRisk(p: RosterPlayer): boolean {
  return p.tier === 'Risky'
}

export interface Flag {
  id: 'risky-top' | 'older' | 'injured' | 'no-tier' | 'bad-season'
  text: string
}

/** "A", "A and B", "A, B and C". */
export function listNames(names: string[]): string {
  return names.length <= 1 ? (names[0] ?? '') : `${names.slice(0, -1).join(', ')} and ${names.at(-1)}`
}

/** "1 player is", "3 players are" (and has/have). */
const players = (n: number, verb: 'is' | 'has') =>
  n === 1 ? `1 player ${verb}` : `${n} players ${verb === 'is' ? 'are' : 'have'}`

/**
 * Warnings for a roster, most serious first. `perGame` ranks the top players by
 * production per game (not by games, which would hide the risk being flagged);
 * players without a value rank by recent minutes after those with one.
 * `outlook` is the simulation's bad season and most possible games left.
 */
export function rosterFlags(
  roster: RosterPlayer[],
  outlook: { low: number; maxRest: number },
  perGame: (p: RosterPlayer) => number | null,
): Flag[] {
  const flags: Flag[] = []
  if (roster.length === 0) return flags

  const top = [...roster]
    .sort((a, b) => (perGame(b) ?? -Infinity) - (perGame(a) ?? -Infinity) || b.recentMinutes - a.recentMinutes)
    .slice(0, RULES.topCount)
  const riskyTop = top.filter(isHighRisk)
  if (riskyTop.length >= RULES.riskyTopMin)
    flags.push({
      id: 'risky-top',
      text: `${riskyTop.length} of your top ${top.length} players are high-risk (Risky availability tier): ${listNames(riskyTop.map((p) => p.name))}.`,
    })

  const totalRest = roster.reduce((s, p) => s + p.rest, 0)
  const older = roster.filter((p) => p.age !== null && p.age >= RULES.olderAge)
  const olderShare = totalRest > 0 ? older.reduce((s, p) => s + p.rest, 0) / totalRest : 0
  if (older.length > 0 && olderShare >= RULES.olderShareMin)
    flags.push({
      id: 'older',
      text: `Your roster depends heavily on players ${RULES.olderAge} or older: ${listNames(older.map((p) => p.name))} ${older.length === 1 ? 'is' : 'are'} expected to play ${Math.round(olderShare * 100)}% of its games left.`,
    })

  const injured = roster.filter(isInjured)
  if (injured.length >= RULES.injuredMin)
    flags.push({ id: 'injured', text: `${players(injured.length, 'is')} injured right now: ${listNames(injured.map((p) => p.name))}.` })

  const noTier = roster.filter((p) => p.tier === null)
  if (noTier.length >= RULES.noTierMin)
    flags.push({
      id: 'no-tier',
      text: `${players(noTier.length, 'has')} no availability tier (rookies, comebacks or players outside a regular rotation), so their forecasts are harder to judge: ${listNames(noTier.map((p) => p.name))}.`,
    })

  if (outlook.maxRest > 0 && outlook.low / outlook.maxRest < RULES.badSeasonShareMax)
    flags.push({
      id: 'bad-season',
      text: `In a bad season (1 in 10), your roster plays only ${Math.round((outlook.low / outlook.maxRest) * 100)}% of its possible games from here on.`,
    })
  return flags
}
