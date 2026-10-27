import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { playedText, soFarText } from '../data'
import TierPill from './TierPill'
import type { PlayerSummary } from '../types'

const PAGE = 50

/**
 * Forecasts, highest first. Comeback players show their if-healthy number with a
 * dashed bar and their setback chance, so they aren't mistaken for regular forecasts.
 */
export default function Leaderboard({
  players,
  dataThrough,
  forecastSeason,
  seasonStarted,
  showTeam = true,
}: {
  players: PlayerSummary[]
  dataThrough: string
  forecastSeason: string
  seasonStarted: boolean
  showTeam?: boolean
}) {
  const navigate = useNavigate()
  const [shown, setShown] = useState(PAGE)
  const rows = players.slice(0, shown)

  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-surface">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs tracking-wide text-faint uppercase">
            <th className="w-10 py-3 pl-4 font-medium">#</th>
            <th className="py-3 pr-3 font-medium">Player</th>
            <th className="hidden py-3 pr-3 font-medium sm:table-cell">Age</th>
            <th className="hidden py-3 pr-3 font-medium md:table-cell">Played {dataThrough}</th>
            {seasonStarted && <th className="hidden py-3 pr-3 font-medium lg:table-cell">{forecastSeason} so far</th>}
            <th className="py-3 pr-3 font-medium">Preseason</th>
            {seasonStarted && <th className="hidden py-3 pr-4 font-medium sm:table-cell">Updated</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((p, i) => (
            <tr
              key={p.id}
              onClick={() => navigate(`/player/${p.id}`)}
              className="cursor-pointer border-b border-line/60 transition last:border-0 hover:bg-surface-2"
            >
              <td className="tabular py-3 pl-4 text-faint">{i + 1}</td>
              <td className="py-3 pr-3">
                <Link
                  to={`/player/${p.id}`}
                  onClick={(e) => e.stopPropagation()}
                  className="font-medium text-ink outline-none focus-visible:underline"
                >
                  {p.name}
                </Link>
                {showTeam && <span className="ml-2 text-xs text-faint">{p.team ?? 'No team'}</span>}
                {p.tier && (
                  <span className="ml-2 hidden align-middle lg:inline">
                    <TierPill tier={p.tier} />
                  </span>
                )}
              </td>
              <td className="tabular hidden py-3 pr-3 text-muted sm:table-cell">{p.age}</td>
              <td className="tabular hidden py-3 pr-3 text-muted md:table-cell">
                {p.comeback ? 'Missed season' : playedText(p.games, p.seasonGames)}
              </td>
              {seasonStarted && (
                <td className="tabular hidden py-3 pr-3 text-muted lg:table-cell">{soFarText(p) ?? '—'}</td>
              )}
              <td className="py-3 pr-3">
                <ForecastCell player={p} />
              </td>
              {seasonStarted && (
                <td className="tabular hidden py-3 pr-4 sm:table-cell">
                  {p.override?.indefinite ? (
                    <span title={p.override.note} className="text-xs font-semibold text-risky">
                      Out indefinitely
                    </span>
                  ) : p.updated === null ? (
                    <span className="text-xs text-faint">{p.notOnRoster ? 'Not on a roster' : '—'}</span>
                  ) : (
                    <>
                      <span className="font-display text-lg font-bold">{Math.round(p.updated)}</span>
                      <UpdatedChange player={p} />
                    </>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {players.length > shown && (
        <button
          onClick={() => setShown(players.length)}
          className="w-full border-t border-line py-3 text-sm font-medium text-muted transition hover:bg-surface-2 hover:text-ink"
        >
          Show all {players.length} players
        </button>
      )}
    </div>
  )
}

/**
 * Change from the preseason forecast, shown only when the updated forecast falls
 * outside the preseason's likely range, so early-season noise doesn't look like news.
 */
function UpdatedChange({ player: p }: { player: PlayerSummary }) {
  if (p.updated === null || p.preLow === null || p.preHigh === null) return null
  if (p.updated >= p.preLow && p.updated <= p.preHigh) return null
  const diff = Math.round(p.updated - p.forecast)
  return (
    <span className={`ml-1.5 text-xs ${diff > 0 ? 'text-up' : 'text-down'}`}>
      {diff > 0 ? '▲' : '▼'} {Math.abs(diff)}
    </span>
  )
}

function ForecastCell({ player: p }: { player: PlayerSummary }) {
  const pct = `${(p.shown / 82) * 100}%`
  return (
    <div className="flex items-center gap-3">
      <div className="relative hidden h-2 w-24 shrink-0 rounded-full bg-surface-2 sm:block">
        <div
          className={`absolute inset-y-0 left-0 rounded-full ${p.comeback ? 'border border-dashed border-accent bg-accent/15' : 'bg-accent'}`}
          style={{ width: pct }}
        />
      </div>
      <span className="tabular whitespace-nowrap">
        <span className="font-display text-lg font-bold">{Math.round(p.shown)}</span>
        {p.comeback ? (
          <span className="ml-1.5 text-xs text-muted">
            if healthy · <span className="text-ink">{Math.round((p.setbackChance ?? 0) * 100)}%</span> setback
          </span>
        ) : (
          <span className="ml-1 text-xs text-faint">games</span>
        )}
      </span>
    </div>
  )
}
