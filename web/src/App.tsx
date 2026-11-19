import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from 'react-router'
import SearchBox from './components/SearchBox'
import { latestFinishedSeason, shortDate, useIndex } from './data'
import Home from './pages/Home'
import MyRoster from './pages/MyRoster'
import Rankings from './pages/Rankings'
import { isCurrent, menuActive, MENUS, type NavItem } from './nav'
import { LEGACY_PATHS, legacyRedirect } from './redirects'

// The player and How it works pages carry the chart library, so they load only when first opened.
const Player = lazy(() => import('./pages/Player'))
const HowItWorks = lazy(() => import('./pages/HowItWorks'))
import type { Index } from './types'

export default function App() {
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <Shell />
    </BrowserRouter>
  )
}

function Shell() {
  const index = useIndex()
  const { pathname, hash } = useLocation()
  // New page: start at the top, unless the link points at a part of it (#accuracy).
  useEffect(() => {
    if (!hash) window.scrollTo(0, 0)
  }, [pathname, hash])

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-30 border-b border-line bg-bg/85 backdrop-blur">
        <div className="mx-auto flex max-w-4xl items-center gap-3 px-4 py-3 sm:gap-4 sm:px-6">
          <Link to="/" className="leading-none">
            <span className="font-display text-2xl font-extrabold tracking-tight uppercase">
              Next<span className="text-accent">82</span>
            </span>
            {index && <DataDate index={index} />}
          </Link>
          <nav className="ml-auto flex items-center gap-1 sm:gap-2">
            {index && pathname !== '/' && (
              <div className="mr-2 hidden w-56 md:block">
                <SearchBox players={index.players} size="compact" />
              </div>
            )}
            {MENUS.map((m, i) => (
              <NavMenu key={m.label} label={m.label} items={m.items} align={i === MENUS.length - 1 ? 'right' : 'left'} />
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto w-full max-w-4xl flex-1 px-4 sm:px-6">
        {!index ? (
          <p className="py-16 text-muted">Loading forecasts…</p>
        ) : (
          <>
            <StaleWarning index={index} />
            <Routes>
              <Route path="/" element={<Home index={index} />} />
              <Route
                path="/player/:id"
                element={
                  <Suspense fallback={<p className="py-16 text-muted">Loading…</p>}>
                    <Player meta={index.meta} />
                  </Suspense>
                }
              />
              <Route path="/rankings" element={<Rankings meta={index.meta} teams={index.teams} />} />
              <Route path="/roster" element={<MyRoster index={index} />} />
              <Route
                path="/how-it-works"
                element={
                  <Suspense fallback={<p className="py-16 text-muted">Loading…</p>}>
                    <HowItWorks meta={index.meta} />
                  </Suspense>
                }
              />
              {LEGACY_PATHS.map((path) => (
                <Route key={path} path={path} element={<LegacyRedirect />} />
              ))}
              <Route path="*" element={<p className="py-16 text-muted">Page not found.</p>} />
            </Routes>
          </>
        )}
      </main>

      {index && <Footer index={index} />}
    </div>
  )
}

/** An old address: replaced by where its content lives now, so shared links keep working. */
function LegacyRedirect() {
  const { pathname, search } = useLocation()
  return <Navigate to={legacyRedirect(pathname, search) ?? '/'} replace />
}

/** A header menu: tap or click to open; closes on Escape, a tap elsewhere or navigation
 * (it remembers the page it was opened on and counts as open only there). */
function NavMenu({ label, items, align = 'left' }: { label: string; items: NavItem[]; align?: 'left' | 'right' }) {
  const location = useLocation()
  // The whole address, so picking a view or part of the same page also closes the menu.
  const here = location.pathname + location.search + location.hash
  const [openOn, setOpenOn] = useState<string | null>(null)
  const open = openOn === here
  const setOpen = (next: boolean | ((was: boolean) => boolean)) =>
    setOpenOn((typeof next === 'function' ? next(open) : next) ? here : null)
  const ref = useRef<HTMLDivElement>(null)
  const active = menuActive(items, location.pathname)
  useEffect(() => {
    if (!open) return
    const outside = (e: PointerEvent) => !ref.current?.contains(e.target as Node) && setOpenOn(null)
    const escape = (e: KeyboardEvent) => e.key === 'Escape' && setOpenOn(null)
    window.addEventListener('pointerdown', outside)
    window.addEventListener('keydown', escape)
    return () => {
      window.removeEventListener('pointerdown', outside)
      window.removeEventListener('keydown', escape)
    }
  }, [open])
  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="true"
        className={`flex items-center gap-1 rounded-md px-2 py-1.5 text-sm font-medium whitespace-nowrap transition hover:text-ink ${active ? 'text-ink' : 'text-muted'}`}
      >
        {label}
        <span aria-hidden className={`text-[10px] transition ${open ? 'rotate-180' : ''}`}>
          ▾
        </span>
      </button>
      {open && (
        <div
          className={`absolute top-full z-40 mt-1 min-w-44 overflow-hidden rounded-xl border border-line bg-surface py-1 shadow-xl ${align === 'right' ? 'right-0' : 'left-0'}`}
        >
          {items.map((i) => (
            <Link
              key={i.to}
              to={i.to}
              aria-current={isCurrent(i.to, location) ? 'page' : undefined}
              className={`block px-4 py-2.5 text-sm transition hover:bg-surface-2 ${isCurrent(i.to, location) ? 'text-accent' : 'text-ink'}`}
            >
              {i.label}
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}

/** How fresh the numbers are, under the logo on every page: games through a date, or before the season. */
function DataDate({ index }: { index: Index }) {
  const { meta } = index
  return (
    <span className="mt-0.5 block text-[11px] font-medium tracking-wide whitespace-nowrap text-faint">
      {meta.seasonStarted && meta.soFarThrough ? (
        <>
          <span className="sm:hidden">Thru</span>
          <span className="hidden sm:inline">Games thru</span> {shortDate(meta.soFarThrough)}
        </>
      ) : (
        'Preseason'
      )}
    </span>
  )
}

function StaleWarning({ index }: { index: Index }) {
  const latest = latestFinishedSeason()
  if (latest <= index.meta.dataThrough) return null
  return (
    <p className="mt-4 rounded-xl border border-accent/40 bg-accent/10 px-4 py-3 text-sm">
      The {latest} season has finished, but these forecasts only use data through {index.meta.dataThrough}. New
      forecasts are coming.
    </p>
  )
}

function Footer({ index }: { index: Index }) {
  const { meta } = index
  const rosters = meta.rostersAsOf ? new Date(meta.rostersAsOf).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : null
  return (
    <footer className="border-t border-line">
      <div className="mx-auto max-w-4xl space-y-1 px-4 py-6 text-xs text-faint sm:px-6">
        <p className="text-sm font-medium text-muted">
          Data from NBA.com. Unofficial, non-commercial student project, not affiliated with the NBA or its teams.
        </p>
        <p>
          {meta.seasonStarted && meta.soFarThrough && <>Games through {shortDate(meta.soFarThrough)} · </>}
          {rosters && <>Teams as of {rosters} · </>}
          Built from NBA seasons since 1996-97 ·{' '}
          <Link to="/how-it-works#accuracy" className="text-muted underline-offset-2 hover:underline">
            How accurate is it?
          </Link>
        </p>
      </div>
    </footer>
  )
}
