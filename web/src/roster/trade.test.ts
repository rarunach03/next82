import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { RosterPlayer } from './model.ts'
import { parseTrade, rosterAfter, sideValue, togglePlayer, tradeParam, verdict } from './trade.ts'

test('a trade reads from and writes to the URL', () => {
  assert.equal(parseTrade(null), null)
  assert.deepEqual(parseTrade(''), { give: [], get: [] })
  assert.deepEqual(parseTrade('1,2-for-3'), { give: [1, 2], get: [3] })
  assert.deepEqual(parseTrade('-for-3,3,x,-4'), { give: [], get: [3] })
  assert.deepEqual(parseTrade('5'), { give: [5], get: [] })
  assert.deepEqual(parseTrade('1_2-for-3_4'), { give: [1, 2], get: [3, 4] })
  // Nobody is on both sides.
  assert.deepEqual(parseTrade('1,2-for-2,3'), { give: [1, 2], get: [3] })
  assert.equal(tradeParam({ give: [1, 2], get: [3] }), '1_2-for-3')
  assert.equal(tradeParam({ give: [], get: [3] }), '-for-3')
  assert.equal(tradeParam({ give: [], get: [] }), '')
  for (const t of [{ give: [1], get: [] }, { give: [4, 5], get: [6, 7] }]) assert.deepEqual(parseTrade(tradeParam(t)), t)
})

test('picking a player adds or removes them, and moves them off the other side', () => {
  let t = { give: [1], get: [] as number[] }
  t = togglePlayer(t, 'give', 2)
  assert.deepEqual(t, { give: [1, 2], get: [] })
  t = togglePlayer(t, 'give', 1)
  assert.deepEqual(t, { give: [2], get: [] })
  t = togglePlayer(t, 'get', 2)
  assert.deepEqual(t, { give: [], get: [2] })
})

test('the roster after a trade: incoming players take the given players\' places', () => {
  assert.deepEqual(rosterAfter([1, 2, 3, 4], { give: [2], get: [9] }), [1, 9, 3, 4])
  // 2-for-1 frees a place; 1-for-2 adds one at the end.
  assert.deepEqual(rosterAfter([1, 2, 3, 4], { give: [2, 3], get: [9] }), [1, 9, 4])
  assert.deepEqual(rosterAfter([1, 2, 3], { give: [2], get: [8, 9] }), [1, 8, 3, 9])
  // From a shared link: giving someone not on the roster changes nothing; getting someone already there doesn't duplicate.
  assert.deepEqual(rosterAfter([1, 2], { give: [7], get: [2, 9] }), [1, 2, 9])
  assert.deepEqual(rosterAfter([], { give: [7], get: [9] }), [9])
})

function player(perGame: number | null, rest: number, low: number | null, high: number | null): RosterPlayer {
  return {
    perGame: perGame === null ? null : { espn: perGame, yahoo: perGame + 1, cat9: 0 },
    rest,
    restLow: low,
    restHigh: high,
  } as RosterPlayer
}

test('side value: value above replacement with a range from each player\'s games range', () => {
  const side = sideValue([player(30, 50, 30, 60), player(25, 40, null, null), player(null, 60, 40, 70)], 'espn', 20)
  assert.deepEqual(side, { value: 10 * 50 + 5 * 40, low: 10 * 30 + 5 * 40, high: 10 * 60 + 5 * 40, unranked: 1 })
  // Below replacement, more games is worse, so the ends swap.
  assert.deepEqual(sideValue([player(15, 50, 30, 60)], 'espn', 20), { value: -250, low: -300, high: -150, unranked: 0 })
  assert.equal(sideValue([player(30, 50, 30, 60)], 'yahoo', 20).value, 11 * 50)
})

test('verdict: gain, lose, or even within one unit', () => {
  const side = (value: number) => ({ value, low: value, high: value, unranked: 0 })
  assert.deepEqual(verdict(side(100), side(150)), { kind: 'gain', amount: 50 })
  assert.deepEqual(verdict(side(150), side(100)), { kind: 'lose', amount: 50 })
  assert.deepEqual(verdict(side(100), side(100.5)), { kind: 'even' })
})
