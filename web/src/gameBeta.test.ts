import assert from 'node:assert/strict'
import { test } from 'node:test'
import { chance, overrideText, thisWeek, weekLines } from './gameBeta.ts'
import type { GameBeta, UpcomingGame } from './types'

const g = (date: string, p: number, override: UpcomingGame['override'] = null): UpcomingGame => ({ date, opponent: 'BOS', p, override })

const beta = {
  asOf: '2026-11-19',
  weekEnd: '2026-11-22',
  players: {
    '1': [g('2026-11-19', 0.9), g('2026-11-21', 0.8), g('2026-11-23', 0.7)],
    '2': [g('2026-11-20', 0.02, 'injury report'), g('2026-11-22', 0.5)],
  },
} as unknown as GameBeta

test('chances read as whole percents, with near-zero shown as under 5%', () => {
  assert.equal(chance(0.917), '92%')
  assert.equal(chance(0.02), '<5%')
  assert.equal(chance(1), '100%')
})

test('this week runs through Sunday', () => {
  assert.deepEqual(thisWeek(beta.players['1'], beta.weekEnd).map((x) => x.date), ['2026-11-19', '2026-11-21'])
})

test('expected games this week add up each game\'s chance; players without chances are skipped', () => {
  const lines = weekLines([1, 2, 3], beta)
  assert.deepEqual(lines.map((l) => [l.id, l.games]), [[1, 2], [2, 2]])
  assert.ok(Math.abs(lines[0].expected - 1.7) < 1e-9)
  assert.ok(Math.abs(lines[1].expected - 0.52) < 1e-9)
})

test('overridden games say why', () => {
  assert.equal(overrideText(g('2026-11-20', 0.02, 'injury report')), 'Out on the injury report')
  assert.equal(overrideText(g('2026-11-20', 0.02, 'return date')), 'Before the expected return')
  assert.equal(overrideText(g('2026-11-20', 0.6)), null)
})
