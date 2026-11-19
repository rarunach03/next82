import assert from 'node:assert/strict'
import { test } from 'node:test'
import { legacyRedirect } from './redirects.ts'

test('injured and stash pages become views of All players, keeping their filters', () => {
  assert.equal(legacyRedirect('/injured', ''), '/?view=injured')
  assert.equal(legacyRedirect('/injured', '?team=LAL'), '/?view=injured&team=LAL')
  assert.equal(legacyRedirect('/stash/', '?format=cat9&junk=1'), '/?view=stash&format=cat9')
})

test('a shared trade opens in My Roster with the same players and scoring', () => {
  assert.equal(legacyRedirect('/trade', '?a=1,2&b=3&format=yahoo'), '/roster?trade=1_2-for-3&format=yahoo')
  assert.equal(legacyRedirect('/trade', '?b=3'), '/roster?trade=-for-3')
  // No trade picked yet: the trade tester opens empty.
  assert.equal(legacyRedirect('/trade', ''), '/roster?trade=')
})

test('about and accuracy open the matching part of How it works', () => {
  assert.equal(legacyRedirect('/about', ''), '/how-it-works#method')
  assert.equal(legacyRedirect('/accuracy', ''), '/how-it-works#accuracy')
})

test('current addresses are not redirected', () => {
  for (const path of ['/', '/rankings', '/roster', '/how-it-works', '/player/203999']) assert.equal(legacyRedirect(path, '?view=x'), null)
})
