import assert from 'node:assert/strict'
import { test } from 'node:test'
import { listNames, rosterFlags, RULES } from './flags.ts'
import type { RosterPlayer } from './model.ts'

let nextId = 1
function player(overrides: Partial<RosterPlayer> = {}): RosterPlayer {
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
    rest: 55,
    restLow: 40,
    restHigh: 66,
    perGame: { espn: 30, yahoo: 30, cat9: 1 },
    stats: null,
    recentMinutes: 2000,
    ...overrides,
  }
}
const espn = (p: RosterPlayer) => p.perGame?.espn ?? null
const healthy = { low: 500, maxRest: 680 }
const ids = (flags: { id: string }[]) => flags.map((f) => f.id)
const injured = { kind: 'automatic', status: 'Out' } as RosterPlayer['override']

test('a healthy, young, tiered roster has no flags', () => {
  const roster = Array.from({ length: 10 }, () => player())
  assert.deepEqual(rosterFlags(roster, healthy, espn), [])
  assert.deepEqual(rosterFlags([], healthy, espn), [])
})

test('flags risky players among the top 5 per game, by name', () => {
  const stars = [player({ name: 'Star A', tier: 'Risky', perGame: { espn: 50, yahoo: 50, cat9: 5 } }),
    player({ name: 'Star B', tier: 'Risky', perGame: { espn: 48, yahoo: 48, cat9: 4 } }),
    player({ name: 'Star C', tier: 'Risky', perGame: { espn: 46, yahoo: 46, cat9: 4 } })]
  const flags = rosterFlags([...stars, ...Array.from({ length: 7 }, () => player())], healthy, espn)
  assert.equal(flags[0].id, 'risky-top')
  assert.equal(flags[0].text, '3 of your top 5 players are high-risk (Risky availability tier): Star A, Star B and Star C.')
})

test('risky players outside the top 5 are not top-player flags', () => {
  const bench = Array.from({ length: 3 }, () => player({ tier: 'Risky', perGame: { espn: 10, yahoo: 10, cat9: -1 } }))
  const top = Array.from({ length: 5 }, () => player({ perGame: { espn: 40, yahoo: 40, cat9: 3 } }))
  assert.ok(!ids(rosterFlags([...bench, ...top], healthy, espn)).includes('risky-top'))
})

test('one risky top player is under the threshold; a small roster uses its size as "top"', () => {
  assert.equal(RULES.riskyTopMin, 2)
  assert.ok(!ids(rosterFlags([player({ tier: 'Risky' }), ...Array.from({ length: 6 }, () => player())], healthy, espn)).includes('risky-top'))
  const small = rosterFlags([player({ tier: 'Risky' }), player({ tier: 'Risky' }), player()], healthy, espn)
  assert.match(small[0].text, /^2 of your top 3 players/)
})

test('flags a roster that leans on players 33 or older, by share of games left', () => {
  const old = [player({ name: 'Vet A', age: 37, rest: 50 }), player({ name: 'Vet B', age: 33, rest: 50 })]
  const young = Array.from({ length: 3 }, () => player({ rest: 50 }))
  const flag = rosterFlags([...old, ...young], healthy, espn).find((f) => f.id === 'older')
  assert.equal(flag?.text, 'Your roster depends heavily on players 33 or older: Vet A and Vet B are expected to play 40% of its games left.')
  // 32-year-olds and rookies (no age) don't count.
  const notOld = [player({ age: 32 }), player({ age: null }), player()]
  assert.ok(!ids(rosterFlags(notOld, healthy, espn)).includes('older'))
})

test('flags several injured players and several without a tier', () => {
  const roster = [
    player({ name: 'Hurt A', override: injured }),
    player({ name: 'Hurt B', out: { reason: 'injury report', status: 'Out', injury: null, reportUrl: null, gamesAfterReturn: null } }),
    player({ tier: null, noTierReason: 'rookie' }),
    player({ tier: null, noTierReason: 'bench' }),
    player({ tier: null, noTierReason: 'comeback' }),
  ]
  const flags = rosterFlags(roster, healthy, espn)
  assert.equal(flags.find((f) => f.id === 'injured')?.text, '2 players are injured right now: Hurt A and Hurt B.')
  assert.match(flags.find((f) => f.id === 'no-tier')!.text, /^3 players have no availability tier/)
  // Missing games without an injury (a long absence, no report) isn't "injured".
  const absent = [player({ out: { reason: 'long absence, no report', status: null, injury: null, reportUrl: null, gamesAfterReturn: null } }), player()]
  assert.ok(!ids(rosterFlags(absent, healthy, espn)).includes('injured'))
})

test('flags a bad season under 60% of possible games', () => {
  const roster = [player()]
  assert.equal(rosterFlags(roster, { low: 400, maxRest: 680 }, espn)[0].text,
    'In a bad season (1 in 10), your roster plays only 59% of its possible games from here on.')
  assert.deepEqual(rosterFlags(roster, { low: 408, maxRest: 680 }, espn), [])
})

test('players without per-game value rank after those with one', () => {
  const unranked = Array.from({ length: 5 }, () => player({ tier: 'Risky', perGame: null, recentMinutes: 3000 }))
  const ranked = Array.from({ length: 5 }, () => player())
  assert.ok(!ids(rosterFlags([...unranked, ...ranked], healthy, espn)).includes('risky-top'))
})

test('names read as a list', () => {
  assert.equal(listNames([]), '')
  assert.equal(listNames(['A']), 'A')
  assert.equal(listNames(['A', 'B']), 'A and B')
  assert.equal(listNames(['A', 'B', 'C']), 'A, B and C')
})
