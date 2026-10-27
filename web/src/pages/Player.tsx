import { Link, useParams } from 'react-router'
import FactorChart from '../components/FactorChart'
import HistoryChart from '../components/HistoryChart'
import InjuredBadge from '../components/InjuredBadge'
import OverrideNote from '../components/OverrideNote'
import RangeBar from '../components/RangeBar'
import Tip from '../components/Tip'
import { GLOSSARY } from '../glossary'
import TierPill from '../components/TierPill'
import { injuryName, playedText, returnText, shortDate, soFarText, usePlayer } from '../data'
import type { Meta, PlayerDetail } from '../types'

export default function Player({ meta }: { meta: Meta }) {
  const id = Number(useParams().id)
  const p = usePlayer(id)

  if (p === undefined) return <p className="py-16 text-muted">Loading…</p>
  if (p === null)
    return (
      <div className="py-16">
        <p className="text-muted">No forecast for this player.</p>
        <Link to="/" className="mt-4 inline-block text-accent">
          ← All players
        </Link>
      </div>
    )

  const team = p.teamName ?? 'Not on an NBA roster'
  const lead = leadNumbers(p, meta)
  return (
    <article className="pt-8 pb-16">
      <Link to={p.team ? `/?team=${p.team}` : '/'} className="text-sm text-muted transition hover:text-ink">
        ← {p.team ? `${p.teamName}` : 'All players'}
      </Link>

      <header className="mt-4">
        <h1 className="font-display text-5xl leading-none font-extrabold tracking-tight uppercase sm:text-6xl">{p.name}</h1>
        <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-muted">
          <span>
            {team} · Age {p.age}
          </span>
          <InjuredBadge p={p} />
          {p.tier && (
            <span className="inline-flex items-center gap-1.5 text-sm">
              <TierPill tier={p.tier} safeLow={meta.tierSafeLow} riskyLow={meta.setbackGames} label />
            </span>
          )}
        </p>
      </header>

      <section className="mt-6 rounded-2xl border border-line bg-surface px-5 py-6 sm:px-7">
        {lead ? (
          <>
            <p className="text-muted">Expected to play about</p>
            <p className="mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="tabular font-display text-7xl leading-none font-extrabold text-accent">{lead.games}</span>
              <span className="text-xl text-muted">games this season</span>
              {lead.low !== null && lead.high !== null && lead.low !== lead.high && (
                <span className="text-muted">
                  (<Tip tip={GLOSSARY.likelyRange}>likely</Tip>{' '}
                  <span className="tabular text-ink">
                    {lead.low}–{lead.high}
                  </span>
                  )
                </span>
              )}
            </p>
          </>
        ) : (
          <p className="font-display text-4xl font-bold">Not on an NBA roster</p>
        )}
        <p className="mt-4 max-w-2xl text-lg text-ink">{sentence(p, meta)}</p>
        <p className="mt-2 text-sm text-faint">
          {meta.seasonStarted && soFarText(p) && <>Played {soFarText(p)} so far · </>}
          {meta.seasonStarted && meta.updatedAsOf ? `Updated through ${shortDate(meta.updatedAsOf)}` : 'Forecast made before the season'}
        </p>
      </section>

      <section className="mt-10">
        <h2 className="font-display text-2xl font-bold uppercase">Games played by season</h2>
        <div className="mt-2 mb-1 flex gap-5 text-xs text-muted">
          <span className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm bg-played" /> Played
          </span>
          <span className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm bg-accent" /> Expected this season
          </span>
        </div>
        <HistoryChart
          history={p.history}
          forecast={lead?.games ?? p.shown}
          forecastSeason={meta.forecastSeason}
          forecastLabel="Expected"
        />
        <p className="text-xs text-faint">
          {p.history.length} seasons since {p.history[0]?.season}.{' '}
          {p.comeback ? `Missed ${meta.dataThrough}.` : `${playedText(p.games, p.seasonGames)} in ${meta.dataThrough}.`}
        </p>
      </section>

      <details className="group mt-10 rounded-2xl border border-line bg-surface">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-5 py-4 sm:px-7 [&::-webkit-details-marker]:hidden">
          <span>
            <span className="font-display text-2xl font-bold uppercase">Details</span>
            <span className="ml-3 text-sm text-muted">
              Preseason forecast, what drives it{p.override ? ', injury sources' : ''}
            </span>
          </span>
          <span aria-hidden className="text-muted transition group-open:rotate-180">
            ▾
          </span>
        </summary>
        <div className="border-t border-line px-5 pt-2 pb-8 sm:px-7">
          <Details p={p} meta={meta} />
        </div>
      </details>
    </article>
  )
}

/** The headline number and range: the updated forecast once the season is on, else the preseason one. */
function leadNumbers(p: PlayerDetail, meta: Meta): { games: number; low: number | null; high: number | null } | null {
  if (meta.seasonStarted) {
    if (p.updated === null) return null
    return { games: Math.round(p.updated), low: p.updatedLow, high: p.updatedHigh }
  }
  return { games: Math.round(p.forecast), low: p.preLow, high: p.preHigh }
}

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

/** One plain-English sentence: status, injury, return estimate, games expected. */
function sentence(p: PlayerDetail, meta: Meta): string {
  if (!meta.seasonStarted) {
    const base = `Forecast before the season to play about ${Math.round(p.forecast)} of 82 games`
    return p.comeback
      ? `${base}, after missing all of ${meta.dataThrough}: about ${Math.round(p.ifHealthy ?? 0)} if healthy, with a ${Math.round((p.setbackChance ?? 0) * 100)}% chance of a setback.`
      : `${base}.`
  }
  if (p.updated === null)
    return `Not on a team right now, so there's no forecast for this season until signing. Before the season, the forecast was about ${Math.round(p.forecast)} games.`
  const rest = Math.round(p.updatedRest ?? 0)
  const games = `expected to play about ${rest} of the ${p.gamesLeft} games left`
  const injury = injuryName(p)
  const out = injury ? `out (${injury})` : 'out'
  const o = p.override
  if (o?.indefinite || (o && !o.earliestReturn))
    return capitalize(`${out} with no return date yet, so the ${rest} more games expected is a rough middle guess and could be far fewer.`)
  if (o && rest === 0) {
    const when = returnText(o)
    return capitalize(
      `${when.startsWith('out for the season') ? when : `out, ${when}`}${injury ? ` (${injury})` : ''}, so no more games are expected this season.`,
    )
  }
  if (o) return capitalize(`${out}, ${returnText(o)}, which leaves room for about ${rest} of the team's ${p.gamesLeft} remaining games.`)
  if (p.out?.reason === 'injury report') return capitalize(`listed ${out} on the latest injury report with no return date yet, and ${games}.`)
  if (p.absenceStreak !== null && p.absenceStreak >= 2)
    return `Has missed the team's last ${p.absenceStreak} games without being on the injury report, and is ${games}.`
  if (p.playedSoFar === 0 && (p.teamGamesSoFar ?? 0) > 0)
    return `Hasn't played yet this season and isn't listed as injured; ${games}.`
  return `Not on the injury report; has played ${p.playedSoFar} of ${p.teamGamesSoFar} games and is ${games}.`
}

function Details({ p, meta }: { p: PlayerDetail; meta: Meta }) {
  const soFar = meta.seasonStarted ? soFarText(p) : null
  const change = Math.round(p.forecast - (p.games / p.seasonGames) * 82)
  return (
    <>
      {p.override && <OverrideNote override={p.override} />}

      <p className="mt-5 text-sm text-muted">
        {p.tier ? (
          <>
            <Tip tip={GLOSSARY.tier(meta.tierSafeLow, meta.setbackGames)}>Availability tier</Tip>{' '}
            <TierPill tier={p.tier} /> {tierText(p.tier, meta.tierSafeLow, meta.setbackGames)}
          </>
        ) : (
          p.updated !== null &&
          !p.rotationRole &&
          'No availability tier: not in a regular rotation role, so playing time depends more on the coach than on health.'
        )}
      </p>

      <div className={`mt-5 grid gap-px overflow-hidden rounded-2xl border border-line bg-line sm:grid-cols-2 ${p.comeback ? 'lg:grid-cols-4' : 'lg:grid-cols-3'}`}>
        {p.comeback ? (
          <>
            <BigStat value={Math.round(p.ifHealthy ?? 0)} unit="games" label="Preseason forecast, if healthy" note="Made before the season · fixed" accent>
              {p.preLow !== null && p.preHigh !== null && (
                <RangeBar low={p.preLow} point={Math.min(p.ifHealthy ?? p.forecast, p.preHigh)} high={p.preHigh} accent />
              )}
              <p className="mt-1 text-xs text-faint">The likely range includes the chance of a setback.</p>
            </BigStat>
            <BigStat value={Math.round((p.setbackChance ?? 0) * 100)} unit="%" label={`Preseason chance of a setback (fewer than ${meta.setbackGames} games)`} />
          </>
        ) : (
          <BigStat
            value={Math.round(p.forecast)}
            unit="games"
            label={<Tip tip={GLOSSARY.preseason}>Preseason forecast</Tip>}
            note={`Made before the season · fixed · ${change >= 0 ? '+' : '−'}${Math.abs(change)} vs. ${meta.dataThrough}`}
            accent
          >
            {p.preLow !== null && p.preHigh !== null && <RangeBar low={p.preLow} point={p.forecast} high={p.preHigh} accent />}
          </BigStat>
        )}
        {p.updated !== null && (
          <BigStat
            value={Math.round(p.updated)}
            unit="games"
            label={
              <>
                <Tip tip={GLOSSARY.expected}>Expected now</Tip>
                {p.override && ' · with injury news'}
              </>
            }
            note={`${p.playedSoFar ?? 0} played + ${Math.round(p.updatedRest ?? 0)} more of ${p.gamesLeft} left`}
          >
            {p.updatedLow !== null && p.updatedHigh !== null && <RangeBar low={p.updatedLow} point={p.updated} high={p.updatedHigh} />}
          </BigStat>
        )}
        {soFar ? (
          <BigStat
            value={p.playedSoFar ?? 0}
            unit={`of ${p.teamGamesSoFar}`}
            label={`Played so far in ${meta.forecastSeason}`}
            note={
              p.playedSoFar === 0
                ? "Hasn't played yet this season"
                : (streakNote(p.absenceStreak) ?? (meta.soFarThrough ? `Through ${shortDate(meta.soFarThrough)}` : undefined))
            }
          />
        ) : (
          <BigStat value={p.games} unit={`of ${p.seasonGames}`} label={`Played in ${meta.dataThrough}`} />
        )}
      </div>

      {p.b2bLeft !== null && p.b2bRate !== null && meta.b2bLeagueRate !== null && (
        <p className="mt-4 text-sm text-muted">
          <Tip tip={GLOSSARY.b2b}>Back-to-backs</Tip>: {p.team ?? 'The team'} has {p.b2bLeft} left. {p.name} sits the second
          night about {Math.round(p.b2bRate * 100)}% of the time (league average {Math.round(meta.b2bLeagueRate * 100)}%), roughly{' '}
          {Math.max(0, Math.round(p.b2bRate * p.b2bLeft))} game{Math.round(p.b2bRate * p.b2bLeft) === 1 ? '' : 's'}. The
          forecast already counts typical resting.
        </p>
      )}

      {p.comeback ? (
        <p className="mt-4 rounded-xl border border-accent/30 bg-accent/10 px-4 py-3 text-sm text-ink">
          {p.name} didn't play in {meta.dataThrough}. Players returning from a missed season tend to either play a lot or
          barely play, so the preseason forecast has two numbers instead of one. If healthy, past comeback forecasts were
          off by about {Math.round(meta.accuracy.comebackHealthyMae)} games on average.
        </p>
      ) : (
        <p className="mt-4 text-sm text-faint">
          The preseason forecast was made before the season started and stays fixed: its average miss is{' '}
          {meta.accuracy.modelMae} games, and half land within {Math.round(meta.accuracy.modelMedianError)}. The expected
          number adds games played so far to a fresh forecast for the games left
          {meta.accuracy.updatedMae !== undefined && <>, which misses the rest of a season by {meta.accuracy.updatedMae} games on average</>}
          .
        </p>
      )}

      <section className="mt-10">
        <h3 className="font-display text-xl font-bold uppercase">What drives the preseason forecast{p.comeback && ' if healthy'}</h3>
        <p className="mt-1 mb-5 text-sm text-muted">
          The average {p.comeback ? 'healthy comeback' : 'player'} is forecast at {Math.round(p.factorBase)} games. Each
          factor moves this player's forecast up or down.
        </p>
        <FactorChart factors={p.factors} />
      </section>

      {p.similar.length > 0 && (
        <section className="mt-10">
          <h3 className="font-display text-xl font-bold uppercase">Similar past comebacks</h3>
          <p className="mt-1 mb-4 text-sm text-muted">
            Players with a similar age and role who missed a season (for any reason), and how many games they played when
            they came back.
          </p>
          <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-bg">
            {p.similar.map((s) => (
              <li key={s.name + s.seasonMissed} className="flex items-center justify-between gap-4 px-4 py-3">
                <div className="min-w-0">
                  <div className="truncate font-medium">{s.name}</div>
                  <div className="text-xs text-faint">
                    Missed {s.seasonMissed} at {s.age} · season before: {s.before}
                  </div>
                </div>
                <div className="tabular shrink-0 text-right">
                  <span className="font-display text-2xl font-bold">{s.comebackGames}</span>
                  <span className="ml-1 text-xs text-faint">games</span>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  )
}

function tierText(tier: string, safeLow: number, riskyLow: number): string {
  if (tier === 'Safe') return `Even a bad outcome is ${safeLow}+ games.`
  if (tier === 'Risky') return `A bad outcome is fewer than ${riskyLow} games.`
  return `A bad outcome is ${riskyLow}–${safeLow} games.`
}

/** "Out for the team's last 6 games" style note, only for real absences. */
function streakNote(streak: number | null): string | undefined {
  if (streak === null || streak < 2) return undefined
  return `Out for the team's last ${streak} games`
}

function BigStat({
  value,
  unit,
  label,
  note,
  accent = false,
  children,
}: {
  value: number
  unit: string
  label: React.ReactNode
  note?: string
  accent?: boolean
  children?: React.ReactNode
}) {
  return (
    <div className="bg-bg px-5 py-5">
      <div className="text-sm text-muted">{label}</div>
      <div className="mt-1 flex items-baseline gap-2">
        <span className={`tabular font-display text-5xl leading-none font-extrabold ${accent ? 'text-accent' : ''}`}>{value}</span>
        <span className="text-lg text-muted">{unit}</span>
      </div>
      {note && <div className="mt-2 text-sm text-faint">{note}</div>}
      {children}
    </div>
  )
}
