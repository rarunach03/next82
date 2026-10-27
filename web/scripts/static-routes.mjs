// GitHub Pages has no route rewrites, so a link like /next82/player/123 would only
// load through 404.html (with a 404 status that link previews and search engines
// see). Copy the app's index.html to a real page for every route instead.
import { copyFileSync, mkdirSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

const dist = 'dist'
const index = join(dist, 'index.html')
const routes = [
  'about',
  'rankings',
  'accuracy',
  'trade',
  ...readdirSync(join(dist, 'data', 'players')).map((f) => `player/${f.replace('.json', '')}`),
]
for (const route of routes) {
  mkdirSync(join(dist, route), { recursive: true })
  copyFileSync(index, join(dist, route, 'index.html'))
}
copyFileSync(index, join(dist, '404.html'))
console.log(`Wrote ${routes.length} route pages and 404.html`)
