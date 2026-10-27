import { lazy, Suspense, useEffect } from 'react'
import { BrowserRouter, Link, Route, Routes, useLocation } from 'react-router'
import SearchBox from './components/SearchBox'
import { baselineText, latestFinishedSeason, shortDate, useIndex } from './data'
import About from './pages/About'
import Accuracy from './pages/Accuracy'
import Home from './pages/Home'
import Rankings from './pages/Rankings'
import Trade from './pages/Trade'

// The player page carries the chart library, so it loads only when first opened.
const Player = lazy(() => import('./pages/Player'))
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
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [pathname])

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-30 border-b border-line bg-bg/85 backdrop-blur">
        <div className="mx-auto flex max-w-4xl items-center gap-4 px-4 py-3 sm:px-6">
          <Link to="/" className="font-display text-2xl font-extrabold tracking-tight uppercase">
            Next<span className="text-accent">82</span>
          </Link>
          <nav className="ml-auto flex items-center gap-4">
            {index && pathname !== '/' && (
              <div className="hidden w-64 sm:block">
                <SearchBox players={index.players} size="compact" />
              </div>
            )}
            <Link
              to="/rankings"
              className={`text-sm font-medium transition hover:text-ink ${pathname === '/rankings' ? 'text-ink' : 'text-muted'}`}
            >
              Rankings
            </Link>
            <Link
              to="/trade"
              className={`text-sm font-medium transition hover:text-ink ${pathname === '/trade' ? 'text-ink' : 'text-muted'}`}
            >
              Trade
            </Link>
            <Link
              to="/accuracy"
              className={`text-sm font-medium transition hover:text-ink ${pathname === '/accuracy' ? 'text-ink' : 'text-muted'}`}
            >
              Accuracy
            </Link>
            <Link
              to="/about"
              className={`text-sm font-medium transition hover:text-ink ${pathname === '/about' ? 'text-ink' : 'text-muted'}`}
            >
              About
            </Link>
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
              <Route path="/trade" element={<Trade />} />
              <Route path="/accuracy" element={<Accuracy meta={index.meta} />} />
              <Route path="/about" element={<About meta={index.meta} />} />
              <Route path="*" element={<p className="py-16 text-muted">Page not found.</p>} />
            </Routes>
          </>
        )}
      </main>

      {index && <Footer index={index} />}
    </div>
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
          Forecasts use NBA regular seasons from 1996-97 through {meta.dataThrough}
          {rosters && <> · Teams as of {rosters}</>}
          {meta.seasonStarted && meta.soFarThrough && <> · {meta.forecastSeason} games through {shortDate(meta.soFarThrough)}</>}.
        </p>
        <p>
          Forecasts were made before the {meta.forecastSeason} season and stay fixed, so they can be checked against what
          actually happens. Tested on {meta.accuracy.testSeasons.join(' and ')}, seasons the model never saw: our average miss
          was {meta.accuracy.modelMae} games (half within {Math.round(meta.accuracy.modelMedianError)}), vs.{' '}
          {meta.accuracy.bestBaselineMae} {baselineText(meta.accuracy.bestBaseline)}.
        </p>
      </div>
    </footer>
  )
}
