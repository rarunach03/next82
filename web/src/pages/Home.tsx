import { useMemo } from 'react'
import { Link, useSearchParams } from 'react-router'
import Leaderboard from '../components/Leaderboard'
import SearchBox from '../components/SearchBox'
import { baselineText, isInjured, shortDate } from '../data'
import type { Index } from '../types'

export default function Home({ index }: { index: Index }) {
  const { meta, teams, players } = index
  const [params, setParams] = useSearchParams()
  const teamAbbr = params.get('team')?.toUpperCase() ?? ''
  const team = teams.find((t) => t.abbr === teamAbbr)
  // Highest expected games first (the updated forecast once the season is on).
  const rows = useMemo(() => {
    const list = team ? players.filter((p) => p.team === team.abbr) : players
    const key = (p: (typeof players)[number]) => (meta.seasonStarted ? (p.updated ?? -1) : p.shown)
    return [...list].sort((a, b) => key(b) - key(a))
  }, [players, team, meta.seasonStarted])
  const injuredCount = useMemo(() => players.filter(isInjured).length, [players])

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
          <Choice
            to="/rankings"
            title="Fantasy rankings"
            text="Who's worth the most from here on, counting games they'll miss."
          />
          <Choice
            to="/injured"
            title="Who's injured"
            text={`${injuredCount} players out with an injury, and when they're expected back.`}
          />
        </div>
      </section>

      <section className="pb-16">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <h2 className="font-display text-3xl font-bold uppercase">{team ? team.name : 'All players'}</h2>
          <label className="flex items-center gap-2 text-sm text-muted">
            Team
            <select
              value={team?.abbr ?? ''}
              onChange={(e) => setParams(e.target.value ? { team: e.target.value } : {})}
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
        </div>
        <Leaderboard
          key={team?.abbr ?? 'all'}
          players={rows}
          seasonStarted={meta.seasonStarted}
          showTeam={!team}
        />
        {team && team.noForecast.length > 0 && (
          <p className="mt-3 text-sm text-faint">
            No forecast yet: {team.noForecast.join(', ')}. Forecasts need NBA games in {meta.previousSeason} or{' '}
            {meta.dataThrough}, so rookies aren't included.
          </p>
        )}
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

function Choice({ to, title, text }: { to: string; title: string; text: string }) {
  return (
    <Link to={to} className="group rounded-2xl border border-line bg-surface p-4 transition hover:border-accent/60 hover:bg-surface-2">
      <h2 className="font-display text-xl font-bold uppercase">
        {title} <span className="text-accent transition group-hover:translate-x-0.5">→</span>
      </h2>
      <p className="mt-0.5 text-sm text-muted">{text}</p>
    </Link>
  )
}
