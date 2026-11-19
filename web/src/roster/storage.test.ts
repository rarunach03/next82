import assert from 'node:assert/strict'
import { test } from 'node:test'
import { DEFAULT_SEED, parseSaved } from './storage.ts'

test('nothing saved, or unreadable data, gives an empty roster and the default seed', () => {
  for (const raw of [null, '', 'not json', '42', 'null', '{"ids":"1,2"}'])
    assert.deepEqual(parseSaved(raw), { ids: [], seed: DEFAULT_SEED }, String(raw))
})

test('keeps whole positive ids once each, at most 13, and the seed', () => {
  const ids = [5, 5, -1, 2.5, 'x', 7, ...Array.from({ length: 20 }, (_, i) => 100 + i)]
  const saved = parseSaved(JSON.stringify({ ids, seed: 1234 }))
  assert.equal(saved.seed, 1234)
  assert.deepEqual(saved.ids.slice(0, 3), [5, 7, 100])
  assert.equal(saved.ids.length, 13)
})
