import { Link } from 'react-router'
import { chance, overrideText } from '../gameBeta'
import type { UpcomingGame } from '../types'

const day = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })

/** Beta: the chance a player plays the next game, and the next five games. */
export default function NextGames({ games }: { games: UpcomingGame[] | undefined }) {
  return (
    <section className="mt-6 rounded-2xl border border-line bg-surface px-5 py-5 sm:px-7">
      <div className="flex items-center gap-2">
        <h2 className="font-display text-2xl font-bold uppercase">Next games</h2>
        <span className="rounded-full border border-accent/50 px-2 py-0.5 text-xs font-semibold text-accent">Beta</span>
      </div>
      {!games || games.length === 0 ? (
        <p className="mt-2 text-sm text-muted">
          Game-by-game chances appear after a player's first game with their current team.
        </p>
      ) : (
        <>
          <p className="mt-3 text-muted">Chance to play next game</p>
          <p className="mt-1 flex flex-wrap items-baseline gap-x-3">
            <span className="tabular font-display text-6xl leading-none font-extrabold text-accent">{chance(games[0].p)}</span>
            <span className="text-muted">
              {day(games[0].date)}
              {games[0].opponent && <> vs. {games[0].opponent}</>}
            </span>
          </p>
          {overrideText(games[0]) && <p className="mt-1 text-sm text-risky">{overrideText(games[0])}</p>}
          <ul className="mt-4 divide-y divide-line border-t border-line">
            {games.slice(0, 5).map((g) => (
              <li key={g.date} className="flex items-center gap-3 py-2 text-sm">
                <span className="w-28 shrink-0 text-muted">{day(g.date)}</span>
                <span className="w-14 shrink-0 text-faint">{g.opponent ? `vs. ${g.opponent}` : ''}</span>
                <span className="relative h-2 flex-1 rounded-full bg-surface-2" aria-hidden>
                  <span className="absolute inset-y-0 left-0 rounded-full bg-accent" style={{ width: `${g.p * 100}%` }} />
                </span>
                <span className="tabular w-11 shrink-0 text-right font-semibold">{chance(g.p)}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-faint">
            From a game-by-game model; the next game uses everything known today, later games assume today's status
            carries on. An Out listing or an expected return date sets games before it to under 5%.{' '}
            <Link to="/how-it-works#game-beta" className="text-muted underline-offset-2 hover:underline">
              How it works
            </Link>
          </p>
        </>
      )}
    </section>
  )
}
