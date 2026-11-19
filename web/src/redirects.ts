// Old addresses from before the site was reorganized, sent to where their content
// lives now, so shared links keep working.
import { tradeParam } from './roster/trade.ts'

/** Where an old address now lives (path, query and hash), or null if it isn't an old address. */
export function legacyRedirect(pathname: string, search: string): string | null {
  const params = new URLSearchParams(search)
  const path = pathname.replace(/\/+$/, '') || '/'
  // Keep the filters the old page understood.
  const keep = (names: string[], extra: Record<string, string>) => {
    const next = new URLSearchParams(extra)
    for (const n of names) {
      const v = params.get(n)
      if (v) next.set(n, v)
    }
    return next.toString()
  }
  switch (path) {
    case '/injured':
      return `/?${keep(['team'], { view: 'injured' })}`
    case '/stash':
      return `/?${keep(['team', 'format'], { view: 'stash' })}`
    case '/trade': {
      // The trade analyzer's sides (?a=give&b=get) become a trade on My Roster.
      const side = (name: string) => (params.get(name) ?? '').split(',').map(Number).filter((n) => Number.isInteger(n) && n > 0)
      return `/roster?${keep(['format'], { trade: tradeParam({ give: side('a'), get: side('b') }) })}`
    }
    default:
      return null
  }
}

/** Old addresses that redirect (for the router). */
export const LEGACY_PATHS = ['/injured', '/stash', '/trade']
