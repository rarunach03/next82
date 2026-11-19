import assert from 'node:assert/strict'
import { test } from 'node:test'
import { DEFAULT_SPREAD, drawGames, histogram, normalDraws, quantile, seededRandom, simulate, spread, type PlayerGames } from './simulate.ts'

const player = (rest: number, restLow: number | null, restHigh: number | null, gamesLeft = 70, playedSoFar = 12): PlayerGames => ({
  playedSoFar,
  gamesLeft,
  rest,
  restLow,
  restHigh,
})

test('the same seed gives the same simulation; another seed differs', () => {
  const roster = [player(55, 31, 65), player(40, 10, 62), player(66, 50, 70)]
  assert.deepEqual(simulate(roster, 82).totals, simulate(roster, 82).totals)
  assert.notDeepEqual(simulate(roster, 82).totals, simulate(roster, 7).totals)
})

test('draws are whole games inside [0, games left]', () => {
  const s = spread(player(30, 0, 70))
  const z = normalDraws(seededRandom(1))
  for (let i = 0; i < 20000; i++) {
    const g = drawGames(s, z() * 3)
    assert.ok(Number.isInteger(g) && g >= 0 && g <= 70, `${g}`)
  }
})

test('about 1 in 10 draws land below the range and 1 in 10 above it', () => {
  const s = spread(player(40, 20, 60, 82))
  const z = normalDraws(seededRandom(3))
  const n = 40000
  let below = 0
  let above = 0
  for (let i = 0; i < n; i++) {
    const g = drawGames(s, z())
    if (g < 20) below++
    if (g > 60) above++
  }
  // Rounding to whole games moves a little mass across each end.
  assert.ok(Math.abs(below / n - 0.1) < 0.02, `below ${below / n}`)
  assert.ok(Math.abs(above / n - 0.1) < 0.02, `above ${above / n}`)
})

test('a lopsided range stays lopsided', () => {
  const s = spread(player(60, 30, 66))
  const z = normalDraws(seededRandom(5))
  const draws = Array.from({ length: 20000 }, () => drawGames(s, z())).sort((a, b) => a - b)
  assert.ok(60 - quantile(draws, 0.1) > 3 * (quantile(draws, 0.9) - 60))
})

test('a player sure to play every game always does', () => {
  const sim = simulate([player(70, 70, 70)], 1, 500)
  assert.equal(sim.low, 70)
  assert.equal(sim.high, 70)
})

test('players without a range get the default spread, kept inside [0, games left]', () => {
  assert.deepEqual(spread(player(60, null, null, 68)), { point: 60, low: 60 - DEFAULT_SPREAD * 68, high: 68, max: 68 })
  // Ranges that miss the forecast after rounding are widened to contain it.
  assert.deepEqual(spread(player(30.4, 31, 50)), { point: 30.4, low: 30.4, high: 50, max: 70 })
})

test('roster totals: bad <= median <= good, centred near the summed forecasts', () => {
  const roster = [player(35, 15, 55), player(50, 30, 65), player(45, 25, 62), player(20, 2, 40)]
  const sim = simulate(roster, 82)
  assert.ok(sim.low <= sim.median && sim.median <= sim.high)
  assert.equal(sim.forecastSum, 150)
  // Symmetric ranges: the typical and average totals sit near the summed forecasts.
  assert.ok(Math.abs(sim.median - sim.forecastSum) <= 3, `${sim.median}`)
  assert.ok(Math.abs(sim.mean - sim.forecastSum) <= 3, `${sim.mean}`)
  assert.equal(sim.maxRest, 280)
  assert.equal(sim.played, 48)
  assert.ok(sim.totals.every((t) => t >= 0 && t <= sim.maxRest))
})

test('independent players: the roster range is narrower than the sum of player ranges', () => {
  const roster = Array.from({ length: 10 }, () => player(45, 25, 62))
  const sim = simulate(roster, 82)
  assert.ok(sim.high - sim.low < 10 * (62 - 25))
})

test('an empty roster simulates to zero', () => {
  const sim = simulate([], 82, 100)
  assert.equal(sim.median, 0)
  assert.equal(sim.maxRest, 0)
  assert.deepEqual(sim.bins, [{ from: 0, to: 0, count: 100 }])
})

test('histogram bins cover every value once', () => {
  const values = Int32Array.from({ length: 1000 }, (_, i) => 300 + (i % 97))
  values.sort()
  const bins = histogram(values, 16)
  assert.ok(bins.length <= 16)
  assert.equal(bins.reduce((s, b) => s + b.count, 0), 1000)
  assert.equal(bins[0].from, 300)
  assert.ok(bins.at(-1)!.to >= 396)
})

test('quantile uses the nearest rank', () => {
  const sorted = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
  assert.equal(quantile(sorted, 0.1), 1)
  assert.equal(quantile(sorted, 0.5), 5)
  assert.equal(quantile(sorted, 0.9), 9)
  assert.equal(quantile([], 0.5), 0)
})

test('long low tails: the expected roster total is below the summed forecasts', () => {
  // Forecasts are each player's middle outcome; injuries cost more games than luck adds.
  const roster = Array.from({ length: 10 }, () => player(55, 31, 65, 69))
  const sim = simulate(roster, 82)
  assert.ok(sim.mean < sim.forecastSum - 20, `${sim.mean} vs ${sim.forecastSum}`)
  assert.ok(sim.low <= sim.mean && sim.mean <= sim.high)
})
