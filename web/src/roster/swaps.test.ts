import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { RosterPlayer } from './model.ts'
import { isSafer, positionsOverlap, swapSuggestions } from './swaps.ts'

let nextId = 1
function player(pts: number, overrides: Partial<RosterPlayer> = {}): RosterPlayer {
  const id = nextId++
  return {
    id,
    name: `Player ${id}`,
    search: `player ${id}`,
    team: 'BOS',
    position: 'G',
    age: 26,
    tier: 'Safe',
    noTierReason: null,
    rookie: false,
    override: null,
    out: null,
    playedSoFar: 12,
    gamesLeft: 68,
    rest: 60,
    restLow: 45,
    restHigh: 68,
    perGame: { espn: pts, yahoo: pts, cat9: 0 },
    stats: { MIN: 30, PTS: pts, REB: 5, AST: 4, STL: 1, BLK: 0.5, FG3M: 2, TOV: 2 },
    recentMinutes: 2000,
    ...overrides,
  }
}

test('positions overlap when they share a letter; unknown matches anything', () => {
  assert.ok(positionsOverlap('G-F', 'F-C'))
  assert.ok(positionsOverlap('C', 'C-F'))
  assert.ok(!positionsOverlap('G', 'C'))
  assert.ok(positionsOverlap(null, 'C'))
})

test('safer means a better tier, more games left and not injured', () => {
  const risky = player(25, { tier: 'Risky', rest: 30 })
  assert.ok(isSafer(player(25, { tier: 'Moderate', rest: 40 }), risky))
  assert.ok(!isSafer(player(25, { tier: 'Risky', rest: 50 }), risky))
  assert.ok(!isSafer(player(25, { tier: 'Safe', rest: 25 }), risky))
  assert.ok(!isSafer(player(25, { tier: null, rest: 60 }), risky))
  assert.ok(!isSafer(player(25, { rest: 60, override: { kind: 'news' } as RosterPlayer['override'] }), risky))
})

test('suggests the most similar safer players at the same position, nearest first', () => {
  const risky = player(25, { tier: 'Risky', rest: 30 })
  const near = player(24.5)
  const close = player(23)
  const far = player(12)
  const farther = player(8)
  const center = player(25, { position: 'C' })
  const alsoRisky = player(25, { tier: 'Risky', rest: 50 })
  const onRoster = player(25)
  const pool = [risky, far, near, farther, center, alsoRisky, close, onRoster]
  const swaps = swapSuggestions(risky, pool, new Set([risky.id, onRoster.id]))
  assert.deepEqual(swaps.map((s) => s.player.id), [near.id, close.id, far.id])
  assert.ok(swaps[0].distance < swaps[1].distance)
})

test('no suggestions without per-game stats, and fewer when few qualify', () => {
  const noStats = player(25, { tier: 'Risky', rest: 30, stats: null })
  assert.deepEqual(swapSuggestions(noStats, [noStats, player(25)], new Set()), [])
  const risky = player(25, { tier: 'Risky', rest: 30 })
  assert.equal(swapSuggestions(risky, [risky, player(20)], new Set([risky.id])).length, 1)
})
