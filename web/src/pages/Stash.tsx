import { useSearchParams } from 'react-router'
import { useNavigate } from 'react-router'
import InjuredBadge from '../components/InjuredBadge'
import Tip from '../components/Tip'
import { GLOSSARY } from '../glossary'
import { fantasyValue, injuryName, isInjured, shortDate, useFantasy } from '../data'
import type { FantasyFormat, FantasyPlayer } from '../types'

const FORMATS: { id: FantasyFormat; label: string }[] = [
  { id: 'espn', label: 'ESPN points' },
  { id: 'yahoo', label: 'Yahoo points' },
  { id: 'cat9', label: '9-cat' },
]

function expectedReturn(p: FantasyPlayer): string {
  const o = p.override
  if (!o) return p.out?.status === 'Out' ? 'Not announced' : '–'
  if (o.indefinite || !o.earliestReturn) return 'Indefinite'
  return o.latestReturn ? `${shortDate(o.earliestReturn)}–${shortDate(o.latestReturn)}` : `No earlier than ${shortDate(o.earliestReturn)}`
}

/** Players who are out now but worth holding: rest-of-season value after their return. */
export default function Stash() {
  const fantasy = useFantasy()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const format = (params.get('format') as FantasyFormat) || 'espn'
  if (fantasy === undefined) return <p className="py-16 text-muted">Loading…</p>
  if (fantasy === null) return <p className="py-16 text-muted">Fantasy values aren't available yet.</p>

  const replacement = fantasy.replacement[format]
  const rows = fantasy.players
    .filter((p) => p.out && !p.rookie)
    .map((p) => ({ p, value: fantasyValue(p.perGame[format], replacement, p.restGames) }))
    .filter((r) => r.value > 0)
    .sort((a, b) => b.value - a.value)
  const fmt = (v: number) => Math.round(v).toLocaleString('en-US')

  return (
    <article className="pt-10 pb-16">
      <p className="text-sm font-semibold tracking-widest text-accent uppercase">Fantasy</p>
      <h1 className="mt-2 font-display text-5xl leading-none font-extrabold tracking-tight uppercase">Who to stash</h1>
      <p className="mt-4 max-w-2xl text-muted">
        Players who are out right now but still worth a roster spot: what they're worth{' '}
        <Tip tip={GLOSSARY.aboveReplacement(fantasy.poolSize)}>above a free-agent pickup</Tip>, counting only the games
        they're expected to play after they return. Highest value first.
      </p>
      <div className="mt-6" role="radiogroup" aria-label="Scoring">
        <div className="mb-1 text-xs text-faint">
          Scoring (<Tip tip={GLOSSARY.cat9}>what's 9-cat?</Tip>)
        </div>
        <div className="inline-flex rounded-lg border border-line bg-surface p-0.5">
          {FORMATS.map((f) => (
            <button
              key={f.id}
              role="radio"
              aria-checked={format === f.id}
              onClick={() => setParams(f.id === 'espn' ? {} : { format: f.id }, { replace: true })}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
                format === f.id ? 'bg-accent text-bg' : 'text-muted hover:text-ink'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-5 overflow-x-auto rounded-2xl border border-line bg-surface">
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
                  {isInjured(p) ? (
                    <InjuredBadge p={p} />
                  ) : (
                    <span className="text-xs font-semibold text-muted">Missing games</span>
                  )}
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
        Hover or tap "Injured" for where the information comes from (the official NBA injury report, a team timeline in
        the news, or a recovery estimate). "Missing games": out for 5+ straight team games without being on the injury
        report. Full details and sources are on each player's page.
      </p>
    </article>
  )
}
