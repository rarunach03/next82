import { useMemo } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import InjuredBadge from '../components/InjuredBadge'
import { injuryName, isInjured, returnText, shortDate } from '../data'
import type { Index } from '../types'

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

/** Everyone currently injured: the injury, when they're expected back, and games expected. */
export default function Injured({ index }: { index: Index }) {
  const { meta, teams, players } = index
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const team = params.get('team') ?? ''
  // Best-known players first (most minutes in their last season).
  const rows = useMemo(
    () =>
      players
        .filter((p) => isInjured(p) && (!team || p.team === team))
        .sort((a, b) => b.recentMinutes - a.recentMinutes),
    [players, team],
  )

  return (
    <article className="pt-10 pb-16">
      <p className="text-sm font-semibold tracking-widest text-accent uppercase">Players</p>
      <h1 className="mt-2 font-display text-5xl leading-none font-extrabold tracking-tight uppercase">Who's injured</h1>
      <p className="mt-4 max-w-2xl text-muted">
        Players listed Out with an injury on the NBA's official injury report, or with a known return timeline,
        best-known players first. Tap a player for the full picture.
        {meta.updatedAsOf && <> Updated through {shortDate(meta.updatedAsOf)}.</>}
      </p>

      <label className="mt-6 inline-block">
        <div className="mb-1 text-xs text-faint">Team</div>
        <select
          value={team}
          onChange={(e) => setParams(e.target.value ? { team: e.target.value } : {}, { replace: true })}
          className="rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-accent"
        >
          <option value="">All teams</option>
          {teams.map((t) => (
            <option key={t.abbr} value={t.abbr}>
              {t.name}
            </option>
          ))}
        </select>
      </label>

      <ul className="mt-5 divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">
        {rows.length === 0 && (
          <li className="px-4 py-4 text-faint">No injured players{team ? ' on this team' : ''} right now.</li>
        )}
        {rows.map((p) => {
          const injury = injuryName(p)
          return (
            <li
              key={p.id}
              onClick={() => navigate(`/player/${p.id}`)}
              className="flex cursor-pointer items-start justify-between gap-4 px-4 py-3 transition hover:bg-surface-2"
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <Link to={`/player/${p.id}`} onClick={(e) => e.stopPropagation()} className="font-medium text-ink">
                    {p.name}
                  </Link>
                  <span className="text-xs text-faint">{p.team}</span>
                  <InjuredBadge p={p} />
                </div>
                <div className="mt-0.5 text-sm text-muted">
                  {injury ? capitalize(injury) : 'Injury not specified'}
                  {' · '}
                  {p.override ? returnText(p.override) : 'no return date yet'}
                </div>
              </div>
              {p.updatedRest !== null && p.gamesLeft !== null && (
                <div className="tabular shrink-0 text-right">
                  <span className="font-display text-2xl font-bold">{Math.round(p.updatedRest)}</span>
                  <span className="ml-1 text-xs text-faint">of {p.gamesLeft}</span>
                  <div className="text-xs text-faint">games expected</div>
                </div>
              )}
            </li>
          )
        })}
      </ul>
      <p className="mt-3 text-xs text-faint">
        Games expected: of the team's games left, how many the player is expected to play after returning. Hover or tap
        "Injured" to see where the information comes from.
      </p>
    </article>
  )
}
