// The header's three menus, following the site's story: the forecast (Players), using
// it (Fantasy), trusting it (How it works).

export interface NavItem {
  to: string
  label: string
}

export const MENUS: { label: string; items: NavItem[] }[] = [
  {
    label: 'Players',
    items: [
      { to: '/', label: 'All players' },
      { to: '/?view=injured', label: "Who's injured" },
      { to: '/?view=stash', label: 'Worth stashing' },
    ],
  },
  {
    label: 'Fantasy',
    items: [
      { to: '/rankings', label: 'Rankings' },
      { to: '/roster', label: 'My roster' },
    ],
  },
  {
    label: 'How it works',
    items: [
      { to: '/how-it-works#method', label: 'How the forecasts are made' },
      { to: '/how-it-works#accuracy', label: 'How accurate is it?' },
      { to: '/how-it-works#limits', label: 'Limits' },
    ],
  },
]

/** The menu item for where you are: same page, same All players view, and the same part (if it names one). */
export function isCurrent(to: string, location: { pathname: string; search: string; hash: string }): boolean {
  const target = new URL(to, 'https://next82.local')
  if (target.pathname !== location.pathname) return false
  const view = (search: string) => new URLSearchParams(search).get('view') ?? ''
  if (view(target.search) !== view(location.search)) return false
  return !target.hash || target.hash === location.hash
}

/** A menu is active when you're on one of its pages. */
export function menuActive(items: NavItem[], pathname: string): boolean {
  return items.some((i) => new URL(i.to, 'https://next82.local').pathname === pathname)
}
