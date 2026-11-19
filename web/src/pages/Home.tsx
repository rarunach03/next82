import { useMemo } from 'react'
import { Link, useSearchParams } from 'react-router'
import InjuredTable from '../components/InjuredTable'
import Leaderboard from '../components/Leaderboard'
import ScoringPicker from '../components/ScoringPicker'
import SearchBox from '../components/SearchBox'
import StashTable from '../components/StashTable'
import { baselineText, isInjured, parseFormat, shortDate, useFantasy } from '../data'
import { allPlayers, injuredPlayers, parseView, stashPlayers, VIEWS, type PlayerView } from '../playerViews'
import type { Index } from '../types'

/** All players, with views for who's injured and who's worth stashing. The view and team live in the URL. */
export default function Home({ index }: { index: Index }) {
  const { meta, teams, players } = index
  const [params, setParams] = useSearchParams()
  const view = parseView(params.get('view'))
  const teamAbbr = params.get('team')?.toUpperCase() ?? ''
  const team = teams.find((t) => t.abbr === teamAbbr)
  const format = parseFormat(params.get('format'))
  const fantasy = useFantasy()

  const rows = useMemo(() => allPlayers(players, team?.abbr ?? '', meta.seasonStarted), [players, team, meta.seasonStarted])
  const injured = useMemo(() => injuredPlayers(players, team?.abbr ?? ''), [players, team])
  const injuredCount = useMemo(() => players.filter(isInjured).length, [players])
  const stash = useMemo(
    () => (fantasy ? stashPlayers(fantasy.players, format, fantasy.replacement[format], team?.abbr ?? '') : null),
    [fantasy, format, team],
  )

  // Update from the latest URL, dropping defaults so links stay short.
  function set(key: string, value: string, fallback = '') {
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        if (value === fallback) next.delete(key)
        else next.set(key, value)
        return next
      },
      { replace: true },
    )
  }
  function showView(v: PlayerView) {
    set('view', v, 'all')
    document.getElementById('players')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <>
      <section className="pt-10 pb-8 sm:pt-14">
        <p className="text-sm font-semibold tracking-widest text-accent uppercase">
          {meta.forecastSeason} season
          {meta.seasonStarted && meta.soFarThrough && (
            <span className="ml-2 text-muted">· updated through {shortDate(meta.soFarThrough)}</span>
          )}
        </p>
        <h1 className="mt-2 font-display text-5xl leading-[0.95] font-extrabold tracking-tight uppercase sm:text-7xl">
          How many games
          <br />
          will they play?
        </h1>
        <p className="mt-4 max-w-xl text-muted">
          Every NBA player's expected games this season, updated daily with games played and injury news.
        </p>

        <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div className="rounded-2xl border border-accent/50 bg-surface p-4 sm:col-span-2 lg:col-span-1">
            <h2 className="font-display text-xl font-bold uppercase">Look up a player</h2>
            <p className="mt-0.5 mb-3 text-sm text-muted">Games expected, injuries and why.</p>
            <SearchBox players={players} size="compact" autoFocus />
          </div>
          <Choice to="/rankings" title="Fantasy rankings" text="Who's worth the most from here on, counting games they'll miss." />
          <Choice
            to="/?view=injured"
            onClick={() => showView('injured')}
            title="Who's injured"
            text={`${injuredCount} players out with an injury, and when they're expected back.`}
          />
        </div>
      </section>

      <section id="players" className="scroll-mt-20 pb-16">
        <h2 className="font-display text-3xl font-bold uppercase">{team ? team.name : 'All players'}</h2>
        <div className="mt-3 mb-4 flex flex-wrap items-end gap-3">
          <div role="tablist" aria-label="Show" className="inline-flex rounded-lg border border-line bg-surface p-0.5">
            {VIEWS.map((v) => (
              <button
                key={v.id}
                role="tab"
                aria-selected={view === v.id}
                onClick={() => set('view', v.id, 'all')}
                className={`rounded-md px-3 py-1.5 text-sm font-medium whitespace-nowrap transition ${
                  view === v.id ? 'bg-accent text-bg' : 'text-muted hover:text-ink'
                }`}
              >
                {v.label}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-2 text-sm text-muted">
            Team
            <select
              value={team?.abbr ?? ''}
              onChange={(e) => set('team', e.target.value)}
              className="rounded-lg border border-line bg-surface px-3 py-2 text-ink outline-none focus:border-accent"
            >
              <option value="">All teams</option>
              {teams.map((t) => (
                <option key={t.abbr} value={t.abbr}>
                  {t.name}
                </option>
              ))}
            </select>
          </label>
          {view === 'stash' && <ScoringPicker format={format} onChange={(f) => set('format', f, 'espn')} />}
        </div>

        {view === 'all' && (
          <>
            <Leaderboard key={team?.abbr ?? 'all'} players={rows} seasonStarted={meta.seasonStarted} showTeam={!team} />
            {team && team.noForecast.length > 0 && (
              <p className="mt-3 text-sm text-faint">
                No forecast yet: {team.noForecast.join(', ')}. Forecasts need NBA games in {meta.previousSeason} or{' '}
                {meta.dataThrough}, so rookies aren't included.
              </p>
            )}
          </>
        )}
        {view === 'injured' && <InjuredTable players={injured} team={team?.abbr ?? ''} />}
        {view === 'stash' &&
          (fantasy === undefined ? (
            <p className="py-6 text-muted">Loading…</p>
          ) : stash === null ? (
            <p className="py-6 text-muted">Fantasy values aren't available yet.</p>
          ) : (
            <StashTable rows={stash} />
          ))}

        <p className="mt-6 text-sm text-faint">
          How good are these? Tested on past seasons, the preseason forecasts missed by {meta.accuracy.modelMae} games on
          average, against {meta.accuracy.bestBaselineMae} {baselineText(meta.accuracy.bestBaseline)}.{' '}
          <Link to="/accuracy" className="text-accent">
            See how accurate it is →
          </Link>
        </p>
      </section>
    </>
  )
}

function Choice({ to, title, text, onClick }: { to: string; title: string; text: string; onClick?: () => void }) {
  return (
    <Link
      to={to}
      onClick={
        onClick &&
        ((e) => {
          e.preventDefault()
          onClick()
        })
      }
      className="group rounded-2xl border border-line bg-surface p-4 transition hover:border-accent/60 hover:bg-surface-2"
    >
      <h2 className="font-display text-xl font-bold uppercase">
        {title} <span className="text-accent transition group-hover:translate-x-0.5">→</span>
      </h2>
      <p className="mt-0.5 text-sm text-muted">{text}</p>
    </Link>
  )
}
