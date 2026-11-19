import assert from 'node:assert/strict'
import { test } from 'node:test'
import { allPlayers, injuredPlayers, parseView, stashPlayers } from './playerViews.ts'
import type { FantasyPlayer, OutInfo, Override, PlayerSummary } from './types'

const override = { kind: 'news', status: 'Out' } as Override
const reportOut: OutInfo = { reason: 'injury report', status: 'Out', injury: 'Left knee', reportUrl: null, gamesAfterReturn: 20 }
const absent: OutInfo = { reason: 'long absence, no report', status: null, injury: null, reportUrl: null, gamesAfterReturn: null }

function summary(id: number, o: Partial<PlayerSummary> = {}): PlayerSummary {
  return { id, name: `P${id}`, team: 'BOS', updated: 50, shown: 60, recentMinutes: 1000, override: null, out: null, ...o } as PlayerSummary
}
function fantasyPlayer(id: number, o: Partial<FantasyPlayer> = {}): FantasyPlayer {
  return { id, name: `F${id}`, team: 'BOS', rookie: false, out: reportOut, restGames: 40, perGame: { espn: 30, yahoo: 25, cat9: 1 }, ...o } as FantasyPlayer
}

test('the view comes from the URL; anything unknown is the full list', () => {
  assert.equal(parseView('injured'), 'injured')
  assert.equal(parseView('stash'), 'stash')
  assert.equal(parseView(null), 'all')
  assert.equal(parseView('Injured'), 'all')
})

test('all players: by expected games once the season is on, preseason forecast before; team filter', () => {
  const players = [summary(1, { updated: 40, shown: 70 }), summary(2, { updated: 60, shown: 50 }), summary(3, { updated: null, shown: 80, team: 'LAL' })]
  assert.deepEqual(allPlayers(players, '', true).map((p) => p.id), [2, 1, 3])
  assert.deepEqual(allPlayers(players, '', false).map((p) => p.id), [3, 1, 2])
  assert.deepEqual(allPlayers(players, 'LAL', true).map((p) => p.id), [3])
})

test('injured: an injury adjustment or listed Out with an injury, best-known first', () => {
  const players = [
    summary(1, { override, recentMinutes: 500 }),
    summary(2, { out: reportOut, recentMinutes: 2000 }),
    summary(3, { out: absent }),
    summary(4),
    summary(5, { override, team: 'LAL' }),
  ]
  assert.deepEqual(injuredPlayers(players, '').map((p) => p.id), [2, 5, 1])
  assert.deepEqual(injuredPlayers(players, 'LAL').map((p) => p.id), [5])
})

test('worth stashing: out now, worth more than a free agent from here on, highest value first', () => {
  const players = [
    fantasyPlayer(1, { restGames: 20 }),
    fantasyPlayer(2, { restGames: 40 }),
    fantasyPlayer(3, { out: null }),
    fantasyPlayer(4, { rookie: true }),
    fantasyPlayer(5, { perGame: { espn: 10, yahoo: 10, cat9: -1 } }),
    fantasyPlayer(6, { out: absent, restGames: 30, team: 'LAL' }),
  ]
  const rows = stashPlayers(players, 'espn', 20, '')
  assert.deepEqual(rows.map((r) => r.p.id), [2, 6, 1])
  assert.equal(rows[0].value, (30 - 20) * 40)
  assert.deepEqual(stashPlayers(players, 'yahoo', 20, 'LAL').map((r) => r.p.id), [6])
})
