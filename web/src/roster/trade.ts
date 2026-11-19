// Testing a trade on My Roster: which players go and come, what each side is worth
// from here on, and the roster that results. The trade lives in the URL
// (/roster?trade=1_2-for-3; URLs leave _ alone, unlike commas) so it can be shared.
import type { FantasyFormat } from '../types'
import type { RosterPlayer } from './model.ts'

export interface Trade {
  give: number[]
  get: number[]
}

const ids = (raw: string) => [...new Set(raw.split(/[_,]/).map(Number).filter((n) => Number.isInteger(n) && n > 0))]

/** The trade in the URL, or null when not testing one. An empty value is a trade with nobody picked yet. */
export function parseTrade(raw: string | null): Trade | null {
  if (raw === null) return null
  const [give = '', get = ''] = raw.split('-for-')
  const giveIds = ids(give)
  // A player can't be on both sides.
  return { give: giveIds, get: ids(get).filter((id) => !giveIds.includes(id)) }
}

/** The URL value for a trade: "1_2-for-3", or "" with nobody picked. */
export function tradeParam(t: Trade): string {
  return t.give.length || t.get.length ? `${t.give.join('_')}-for-${t.get.join('_')}` : ''
}

/** Add or remove a player on one side; adding to one side takes them off the other. */
export function togglePlayer(t: Trade, side: keyof Trade, id: number): Trade {
  const other: keyof Trade = side === 'give' ? 'get' : 'give'
  if (t[side].includes(id)) return { ...t, [side]: t[side].filter((i) => i !== id) }
  return { ...t, [side]: [...t[side], id], [other]: t[other].filter((i) => i !== id) } as Trade
}

/**
 * The roster after the trade: players given away leave, players received take the
 * first open places (a given player's slot first), keeping everyone else in order.
 * Players given who aren't on the roster (from a shared link) change nothing.
 */
export function rosterAfter(roster: number[], t: Trade): number[] {
  const incoming = t.get.filter((id) => !roster.includes(id))
  const out: number[] = []
  for (const id of roster) {
    if (!t.give.includes(id)) out.push(id)
    else if (incoming.length) out.push(incoming.shift()!)
  }
  return [...out, ...incoming]
}

export interface SideValue {
  /** Rest-of-season value above replacement, and its likely range from each player's games range. */
  value: number
  low: number
  high: number
  /** Players without per-game value (not ranked); they count as zero. */
  unranked: number
}

/** Rest-of-season value of one side, with a range that adds up each player's bad and good cases. */
export function sideValue(players: RosterPlayer[], format: FantasyFormat, replacement: number): SideValue {
  const total: SideValue = { value: 0, low: 0, high: 0, unranked: 0 }
  for (const p of players) {
    if (!p.perGame) {
      total.unranked++
      continue
    }
    const above = p.perGame[format] - replacement
    const ends = [p.restLow ?? p.rest, p.restHigh ?? p.rest].map((g) => above * g)
    total.value += above * p.rest
    total.low += Math.min(...ends)
    total.high += Math.max(...ends)
  }
  return total
}

export type Verdict = { kind: 'even' } | { kind: 'gain' | 'lose'; amount: number }

/** What the trade does for you: under one unit either way is even. */
export function verdict(give: SideValue, get: SideValue): Verdict {
  const diff = get.value - give.value
  if (Math.abs(diff) < 1) return { kind: 'even' }
  return { kind: diff > 0 ? 'gain' : 'lose', amount: Math.abs(diff) }
}
