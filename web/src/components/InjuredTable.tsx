import { Link, useNavigate } from 'react-router'
import { injuryName, injurySource, returnText } from '../data'
import type { PlayerSummary } from '../types'
import InjuredBadge from './InjuredBadge'

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

/** Injured players: the injury, when they're expected back, where that comes from, and games still expected. */
export default function InjuredTable({ players, team }: { players: PlayerSummary[]; team: string }) {
  const navigate = useNavigate()
  return (
    <>
      <div className="overflow-hidden rounded-2xl border border-line bg-surface">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs tracking-wide text-faint uppercase">
              <th className="py-3 pr-3 pl-4 font-medium">Player</th>
              <th className="hidden py-3 pr-3 font-medium sm:table-cell">Injury and return</th>
              <th className="hidden py-3 pr-3 font-medium lg:table-cell">Source</th>
              <th className="py-3 pr-4 text-right font-medium">Games expected</th>
            </tr>
          </thead>
          <tbody>
            {players.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-4 text-faint">
                  No injured players{team ? ' on this team' : ''} right now.
                </td>
              </tr>
            )}
            {players.map((p) => {
              const injury = injuryName(p)
              const detail = (
                <>
                  {injury ? capitalize(injury) : 'Injury not specified'}
                  <span className="text-faint"> · {p.override ? returnText(p.override) : 'no return date yet'}</span>
                </>
              )
              return (
                <tr
                  key={p.id}
                  onClick={() => navigate(`/player/${p.id}`)}
                  className="cursor-pointer border-b border-line/60 align-top transition last:border-0 hover:bg-surface-2"
                >
                  <td className="py-3 pr-3 pl-4">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <Link to={`/player/${p.id}`} onClick={(e) => e.stopPropagation()} className="font-medium text-ink">
                        {p.name}
                      </Link>
                      <span className="text-xs text-faint">{p.team}</span>
                      <InjuredBadge p={p} />
                    </div>
                    {/* Phones: the injury and return under the name. */}
                    <div className="mt-0.5 text-muted sm:hidden">{detail}</div>
                  </td>
                  <td className="hidden max-w-xs py-3 pr-3 text-muted sm:table-cell">{detail}</td>
                  <td className="hidden max-w-[14rem] py-3 pr-3 text-xs text-muted lg:table-cell">{injurySource(p)}</td>
                  <td className="tabular py-3 pr-4 text-right whitespace-nowrap">
                    {p.updatedRest !== null && p.gamesLeft !== null ? (
                      <>
                        <span className="font-display text-2xl font-bold">{Math.round(p.updatedRest)}</span>
                        <span className="ml-1 text-xs text-faint">of {p.gamesLeft}</span>
                      </>
                    ) : (
                      <span className="text-faint">–</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs text-faint">
        Players listed Out with an injury on the NBA's official injury report, or with a known return timeline,
        best-known players first. Games expected: of the team's games left, how many the player is expected to play after
        returning. Hover or tap "Injured" to see where the information comes from.
      </p>
    </>
  )
}
