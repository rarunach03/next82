import assert from 'node:assert/strict'
import { test } from 'node:test'
import { staleDate, staleSince } from './freshness.ts'

const now = new Date('2026-11-20T12:00:00Z')

test('fresh data is not stale', () => {
  assert.equal(staleSince({ rostersAsOf: '2026-11-20T05:34:53.341317', generatedAt: '2026-11-20T10:20:00+00:00' }, now), null)
})

test('just under two days is not stale; just over is', () => {
  assert.equal(staleSince({ rostersAsOf: null, generatedAt: '2026-11-18T12:30:00+00:00' }, now), null)
  const since = staleSince({ rostersAsOf: null, generatedAt: '2026-11-18T11:30:00+00:00' }, now)
  assert.equal(since?.toISOString(), '2026-11-18T11:30:00.000Z')
})

test('old stats count even when the site was rebuilt today (the Mac was off)', () => {
  const since = staleSince({ rostersAsOf: '2026-11-15T00:30:00.123456', generatedAt: '2026-11-20T10:20:00+00:00' }, now)
  assert.ok(since)
  assert.equal(staleDate(since), 'Nov 15')
})

test('a stale rebuild counts even when the stats are fresh (the cloud failed)', () => {
  assert.ok(staleSince({ rostersAsOf: '2026-11-20T05:00:00', generatedAt: '2026-11-16T10:20:00+00:00' }, now))
})

test('missing or unreadable times are ignored', () => {
  assert.equal(staleSince({ rostersAsOf: null, generatedAt: 'not a date' }, now), null)
  assert.ok(staleSince({ rostersAsOf: 'garbage', generatedAt: '2026-11-01T00:00:00+00:00' }, now))
})
