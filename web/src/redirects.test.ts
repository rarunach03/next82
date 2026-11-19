import assert from 'node:assert/strict'
import { test } from 'node:test'
import { legacyRedirect } from './redirects.ts'

test('injured and stash pages become views of All players, keeping their filters', () => {
  assert.equal(legacyRedirect('/injured', ''), '/?view=injured')
  assert.equal(legacyRedirect('/injured', '?team=LAL'), '/?view=injured&team=LAL')
  assert.equal(legacyRedirect('/stash/', '?format=cat9&junk=1'), '/?view=stash&format=cat9')
})

test('current addresses are not redirected', () => {
  for (const path of ['/', '/rankings', '/roster', '/player/203999']) assert.equal(legacyRedirect(path, '?view=x'), null)
})
