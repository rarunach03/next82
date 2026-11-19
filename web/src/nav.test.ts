import assert from 'node:assert/strict'
import { test } from 'node:test'
import { isCurrent, menuActive, MENUS } from './nav.ts'
import { legacyRedirect } from './redirects.ts'

const at = (path: string) => {
  const url = new URL(path, 'https://next82.local')
  return { pathname: url.pathname, search: url.search, hash: url.hash }
}

test('three menus, five destinations, and no old addresses in them', () => {
  assert.deepEqual(MENUS.map((m) => m.label), ['Players', 'Fantasy', 'How it works'])
  const paths = new Set(MENUS.flatMap((m) => m.items.map((i) => new URL(i.to, 'https://x').pathname)))
  assert.deepEqual([...paths], ['/', '/rankings', '/roster', '/how-it-works'])
  for (const m of MENUS) for (const i of m.items) assert.equal(legacyRedirect(new URL(i.to, 'https://x').pathname, ''), null, i.to)
})

test('the current item matches the page, the All players view and the part', () => {
  assert.ok(isCurrent('/', at('/')))
  assert.ok(isCurrent('/', at('/?team=LAL')))
  assert.ok(!isCurrent('/', at('/?view=injured')))
  assert.ok(isCurrent('/?view=injured', at('/?view=injured&team=LAL')))
  assert.ok(isCurrent('/roster', at('/roster?trade=1-for-2')))
  assert.ok(isCurrent('/how-it-works#accuracy', at('/how-it-works#accuracy')))
  assert.ok(!isCurrent('/how-it-works#accuracy', at('/how-it-works#limits')))
})

test('a menu is active on any of its pages', () => {
  const [players, fantasy, how] = MENUS
  assert.ok(menuActive(players.items, '/'))
  assert.ok(menuActive(fantasy.items, '/roster'))
  assert.ok(!menuActive(fantasy.items, '/'))
  assert.ok(menuActive(how.items, '/how-it-works'))
  assert.ok(!menuActive(players.items, '/player/1'))
})
