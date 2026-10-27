import { useEffect, useState } from 'react'
import type { Fantasy, Index, OutInfo, Override, PlayerDetail, PlayerSummary, SeasonAccuracy } from './types'

/** Where the site is served from: "/" locally, "/next82/" on GitHub Pages. */
const BASE = import.meta.env.BASE_URL

let indexPromise: Promise<Index> | null = null

/** The index (meta, teams, player summaries), fetched once and shared. */
export function useIndex(): Index | null {
  const [index, setIndex] = useState<Index | null>(null)
  useEffect(() => {
    indexPromise ??= fetch(`${BASE}data/index.json`)
      .then((r) => r.json())
      .then((index: Index) => {
        setSeasonEnd(index.meta.regularSeasonEnd ?? null)
        return index
      })
    indexPromise.then(setIndex)
  }, [])
  return index
}

let fantasyPromise: Promise<Fantasy | null> | null = null
let accuracyPromise: Promise<SeasonAccuracy | null> | null = null

/** Season-to-date accuracy. `undefined` while loading, `null` before the season. */
export function useAccuracy(): SeasonAccuracy | null | undefined {
  const [accuracy, setAccuracy] = useState<SeasonAccuracy | null | undefined>(undefined)
  useEffect(() => {
    accuracyPromise ??= fetch(`${BASE}data/accuracy.json`)
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null)
    accuracyPromise.then(setAccuracy)
  }, [])
  return accuracy
}

/** Fantasy values, fetched once. `undefined` while loading, `null` if not exported. */
export function useFantasy(): Fantasy | null | undefined {
  const [fantasy, setFantasy] = useState<Fantasy | null | undefined>(undefined)
  useEffect(() => {
    fantasyPromise ??= fetch(`${BASE}data/fantasy.json`)
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null)
    fantasyPromise.then(setFantasy)
  }, [])
  return fantasy
}

/** One player's details. `undefined` while loading, `null` if not found. */
export function usePlayer(id: number): PlayerDetail | null | undefined {
  // Results are stored with the id they belong to, so switching players shows
  // "loading" straight away instead of the previous player's data.
  const [loaded, setLoaded] = useState<{ id: number; player: PlayerDetail | null } | null>(null)
  useEffect(() => {
    let current = true
    fetch(`${BASE}data/players/${id}.json`)
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null)
      .then((player) => current && setLoaded({ id, player }))
    return () => {
      current = false
    }
  }, [id])
  return loaded?.id === id ? loaded.player : undefined
}

/** Lowercase, accent-free text so "jokic" matches "Jokić". */
export function plain(text: string): string {
  return text.normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase()
}

/**
 * Players matching a search, most likely first: names with a word starting with
 * the query ("james" -> LeBron James, James Harden), then names containing it
 * anywhere. Within each group, players with more recent minutes (better known)
 * come first.
 */
export function searchPlayers(players: PlayerSummary[], query: string, limit = 8): PlayerSummary[] {
  const q = plain(query.trim())
  if (!q) return []
  const scored: [number, PlayerSummary][] = []
  for (const p of players) {
    const wordStart = p.search.startsWith(q) || p.search.split(' ').some((w) => w.startsWith(q))
    const tier = wordStart ? 0 : p.search.includes(q) ? 1 : -1
    if (tier >= 0) scored.push([tier, p])
  }
  scored.sort((a, b) => a[0] - b[0] || b[1].recentMinutes - a[1].recentMinutes)
  return scored.slice(0, limit).map(([, p]) => p)
}

/** Start year of the latest finished regular season (finished from May 1). */
export function latestFinishedSeason(today = new Date()): string {
  const start = today.getMonth() >= 4 ? today.getFullYear() - 1 : today.getFullYear() - 2
  return `${start}-${String(start + 1).slice(-2)}`
}

/** How each simple-guess baseline is described to readers. */
export function baselineText(name: string): string {
  return name === 'Same as last year' ? "guessing last season's total" : "guessing each player's 3-season average"
}

/**
 * Fantasy value above replacement: (per-game score - replacement) x games. Same
 * formula as next82.fantasy.season_value, used by Rankings and Trade.
 */
export function fantasyValue(perGame: number, replacement: number, games: number): number {
  return (perGame - replacement) * games
}

export function shortDate(iso: string): string {
  return new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

/** "2 of 3" games so far, or null before the season or for players without a team. */
export function soFarText(p: { playedSoFar: number | null; teamGamesSoFar: number | null }): string | null {
  if (p.playedSoFar === null || p.teamGamesSoFar === null) return null
  return `${p.playedSoFar} of ${p.teamGamesSoFar}`
}

export function playedText(games: number, seasonGames: number): string {
  return `${games} of ${seasonGames}${games > seasonGames ? ' (traded)' : ''}`
}

/** One-line description of a manual adjustment's status. */
export function overrideStatus(o: Override): string {
  if (o.indefinite) return 'Out indefinitely'
  if (o.estimated && o.earliestReturn && o.latestReturn)
    return `Estimated return ${shortDate(o.earliestReturn)}–${shortDate(o.latestReturn)} (our estimate, not the team's)`
  if (o.estimated && o.earliestReturn)
    return `Estimated return no earlier than ${shortDate(o.earliestReturn)} (our estimate, not the team's)`
  if (o.earliestReturn && o.latestReturn) return `Out · expected back ${shortDate(o.earliestReturn)}–${shortDate(o.latestReturn)}`
  if (o.earliestReturn) return `Out · expected back ${shortDate(o.earliestReturn)} at the earliest`
  return o.status
}

// ---------------------------------------------------------------- injuries, in plain words

type WithInjury = { override: Override | null; out: OutInfo | null }

/** Injured: an injury adjustment, or listed Out with an injury on the team's latest report. */
export function isInjured(p: WithInjury): boolean {
  return p.override !== null || p.out?.reason === 'injury report'
}

/** "left foot fracture", "right achilles tendon (repair / surgery)", or null. */
export function injuryName(p: WithInjury): string | null {
  const raw = p.out?.injury
  if (!raw) return null
  const [body, ...kind] = raw
    .replace(/^Injury\/Illness\s*-\s*/i, '')
    .split(';')
    .map((s) => s.trim().toLowerCase().replace(/\s*\/\s*$/, '').replace(/\b(acl|mcl|pcl|lcl)\b/g, (m) => m.toUpperCase()))
  const extra = kind.filter(Boolean)
  return extra.length ? `${body} (${extra.join(', ')})` : body
}

/** Set once from the index: the regular season's last day, for "out for the season". */
let seasonEnd: string | null = null
export function setSeasonEnd(iso: string | null) {
  seasonEnd = iso
}

const today = () => new Date().toISOString().slice(0, 10)

/** "expected back no earlier than Feb 1 (our estimate)" and similar, in plain words. */
export function returnText(o: Override): string {
  const whose = o.estimated ? 'our estimate' : 'team timeline'
  if (o.indefinite || !o.earliestReturn) return 'out with no return date yet'
  if (seasonEnd && o.earliestReturn.slice(0, 10) > seasonEnd)
    return o.estimated
      ? `not expected back this season (${whose}: ${shortDate(o.earliestReturn)}, ${o.earliestReturn.slice(0, 4)} at the earliest)`
      : `out for the season (${whose})`
  // Window already open: the earliest date has passed.
  if (o.earliestReturn.slice(0, 10) <= today())
    return o.latestReturn ? `could return any day, by ${shortDate(o.latestReturn)} (${whose})` : `could return any day (${whose})`
  if (o.latestReturn) return `expected back between ${shortDate(o.earliestReturn)} and ${shortDate(o.latestReturn)} (${whose})`
  return `expected back no earlier than ${shortDate(o.earliestReturn)} (${whose})`
}

function host(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

/** Where the injury information comes from. */
export function injurySource(p: WithInjury): string {
  const o = p.override
  if (o?.kind === 'news') return `Team timeline reported in the news (${host(o.sourceUrl)})`
  if (o?.kind === 'automatic') return 'Official NBA injury report, with a return estimate from published recovery studies'
  if (o?.kind === 'manual') return `Injury news (${host(o.sourceUrl)}), entered by hand`
  return 'Listed Out on the official NBA injury report'
}
