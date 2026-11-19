import { useNavigate } from 'react-router'
import { injuryName, isInjured, shortDate } from '../data'
import type { StashRow } from '../playerViews'
import type { FantasyPlayer } from '../types'
import InjuredBadge from './InjuredBadge'

function expectedReturn(p: FantasyPlayer): string {
  const o = p.override
  if (!o) return p.out?.status === 'Out' ? 'Not announced' : '–'
  if (o.indefinite || !o.earliestReturn) return 'Indefinite'
  return o.latestReturn ? `${shortDate(o.earliestReturn)}–${shortDate(o.latestReturn)}` : `No earlier than ${shortDate(o.earliestReturn)}`
}

/** Players who are out now but worth holding: rest-of-season value after their return. */
export default function StashTable({ rows }: { rows: StashRow[] }) {
  const navigate = useNavigate()
  const fmt = (v: number) => Math.round(v).toLocaleString('en-US')
  return (
    <>
      <div className="overflow-x-auto rounded-2xl border border-line bg-surface">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs tracking-wide text-faint uppercase">
              <th className="py-3 pr-3 pl-4 font-medium">Player</th>
              <th className="py-3 pr-3 font-medium">Why out</th>
              <th className="hidden py-3 pr-3 font-medium sm:table-cell">Expected return</th>
              <th className="hidden py-3 pr-3 font-medium md:table-cell">Games after return</th>
              <th className="py-3 pr-4 font-medium">Rest-of-season value</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-4 text-faint">
                  Nobody worth stashing right now.
                </td>
              </tr>
            )}
            {rows.map(({ p, value }) => (
              <tr
                key={p.id}
                onClick={() => navigate(`/player/${p.id}`)}
                className="cursor-pointer border-b border-line/60 transition last:border-0 hover:bg-surface-2"
              >
                <td className="py-3 pr-3 pl-4">
                  <span className="font-medium">{p.name}</span>
                  <span className="ml-2 text-xs text-faint">{p.team}</span>
                </td>
                <td className="py-3 pr-3">
                  {isInjured(p) ? <InjuredBadge p={p} /> : <span className="text-xs font-semibold text-muted">Missing games</span>}
                  {injuryName(p) && <div className="mt-0.5 max-w-xs text-xs text-muted">{injuryName(p)}</div>}
                  {p.out!.reportUrl && (
                    <a
                      href={p.out!.reportUrl}
                      target="_blank"
                      rel="noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="text-xs text-accent hover:underline"
                    >
                      Official report ↗
                    </a>
                  )}
                </td>
                <td className="hidden py-3 pr-3 text-muted sm:table-cell">{expectedReturn(p)}</td>
                <td className="tabular hidden py-3 pr-3 text-muted md:table-cell">
                  {p.out!.gamesAfterReturn !== null ? `~${Math.round(p.out!.gamesAfterReturn)}` : '–'}
                </td>
                <td className="tabular py-3 pr-4">
                  <span className="font-semibold">{fmt(value)}</span>
                  <span className="ml-1 text-xs text-faint">over ~{Math.round(p.restGames)} games</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs text-faint">
        Players who are out right now but still worth a roster spot: what they're worth above a free-agent pickup,
        counting only the games they're expected to play after they return. Hover or tap "Injured" for where the
        information comes from (the official NBA injury report, a team timeline in the news, or a recovery estimate).
        "Missing games": out for 5+ straight team games without being on the injury report.
      </p>
    </>
  )
}
