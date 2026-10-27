import { Link, useParams } from 'react-router'
import FactorChart from '../components/FactorChart'
import HistoryChart from '../components/HistoryChart'
import RangeBar from '../components/RangeBar'
import TierPill from '../components/TierPill'
import { playedText, shortDate, soFarText, usePlayer } from '../data'
import type { Meta } from '../types'

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
  const soFar = meta.seasonStarted ? soFarText(p) : null
  const change = Math.round(p.forecast - (p.games / p.seasonGames) * 82)
  return (
    <article className="pt-8 pb-16">
      <Link to={p.team ? `/?team=${p.team}` : '/'} className="text-sm text-muted transition hover:text-ink">
        ← {p.team ? `${p.teamName}` : 'All players'}
      </Link>

      <header className="mt-4">
        <h1 className="font-display text-5xl leading-none font-extrabold tracking-tight uppercase sm:text-6xl">{p.name}</h1>
        <p className="mt-2 text-muted">
          {team} · Age {p.age}
          {p.team && p.team !== p.lastTeam && <span className="text-faint"> · played for {p.lastTeam} in {meta.dataThrough}</span>}
          {!p.team && <span className="text-faint"> · last team {p.lastTeam}</span>}
        </p>
        {p.tier ? (
          <p className="mt-3 flex flex-wrap items-center gap-2 text-sm text-muted">
            <span className="text-faint">Availability tier</span>
            <TierPill tier={p.tier} safeLow={meta.tierSafeLow} riskyLow={meta.setbackGames} />
            {tierText(p.tier, meta.tierSafeLow, meta.setbackGames)}
          </p>
        ) : (
          p.updated !== null &&
          !p.rotationRole && (
            <p className="mt-3 text-sm text-faint">
              No availability tier: not in a regular rotation role, so playing time depends more on the coach than on
              health.
            </p>
          )
        )}
      </header>

      <section className={`mt-8 grid gap-px overflow-hidden rounded-2xl border border-line bg-line sm:grid-cols-2 ${p.comeback ? 'lg:grid-cols-4' : 'lg:grid-cols-3'}`}>
        {p.comeback ? (
          <>
            <BigStat
              value={Math.round(p.ifHealthy ?? 0)}
              unit="games"
              label="Preseason forecast, if healthy"
              note="Made before the season · fixed"
              accent
            >
              {p.preLow !== null && p.preHigh !== null && (
                <RangeBar low={p.preLow} point={Math.min(p.ifHealthy ?? p.forecast, p.preHigh)} high={p.preHigh} accent />
              )}
              <p className="mt-1 text-xs text-faint">The likely range includes the chance of a setback.</p>
            </BigStat>
            <BigStat
              value={Math.round((p.setbackChance ?? 0) * 100)}
              unit="%"
              label={`Preseason chance of a setback (fewer than ${meta.setbackGames} games)`}
            />
          </>
        ) : (
          <BigStat
            value={Math.round(p.forecast)}
            unit="games"
            label="Preseason forecast"
            note={`Made before the season · fixed · ${change >= 0 ? '+' : '−'}${Math.abs(change)} vs. ${meta.dataThrough}`}
            accent
          >
            {p.preLow !== null && p.preHigh !== null && <RangeBar low={p.preLow} point={p.forecast} high={p.preHigh} accent />}
          </BigStat>
        )}
        {p.updated !== null ? (
          <BigStat
            value={Math.round(p.updated)}
            unit="games"
            label={p.comeback ? 'Updated forecast, setback risk included' : 'Updated forecast'}
            note={`${p.playedSoFar ?? 0} played + ${Math.round(p.updatedRest ?? 0)} more of ${p.gamesLeft} left${
              meta.updatedAsOf ? ` · as of ${shortDate(meta.updatedAsOf)}` : ''
            }`}
          >
            {p.updatedLow !== null && p.updatedHigh !== null && (
              <RangeBar low={p.updatedLow} point={p.updated} high={p.updatedHigh} />
            )}
          </BigStat>
        ) : (
          p.notOnRoster && <BigText label="Updated forecast" text="Not on a roster" note="No games this season" />
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
      </section>

      {p.comeback ? (
        <p className="mt-4 rounded-xl border border-accent/30 bg-accent/10 px-4 py-3 text-sm text-ink">
          {p.name} didn't play in {meta.dataThrough}. Players returning from a missed season tend to either play a lot or
          barely play, so this shows two numbers instead of one. If healthy, past comeback forecasts were off by about{' '}
          {Math.round(meta.accuracy.comebackHealthyMae)} games on average. Forecasts were made before the season
          started and stay fixed.
        </p>
      ) : (
        <p className="mt-4 text-sm text-faint">
          The preseason forecast was made before the season started and stays fixed: its average miss is{' '}
          {meta.accuracy.modelMae} games, and half land within {Math.round(meta.accuracy.modelMedianError)}. The updated
          forecast adds games played so far to a fresh prediction for the games left, using every game up to{' '}
          {meta.updatedAsOf ? shortDate(meta.updatedAsOf) : 'now'}
          {meta.accuracy.updatedMae !== undefined && (
            <>
              ; over the rest of a season it misses by {meta.accuracy.updatedMae} games on average
            </>
          )}
          .
        </p>
      )}

      <section className="mt-12">
        <h2 className="font-display text-2xl font-bold uppercase">What's driving the forecast{p.comeback && ' if healthy'}</h2>
        <p className="mt-1 mb-5 text-sm text-muted">
          The average {p.comeback ? 'healthy comeback' : 'player'} is forecast at {Math.round(p.factorBase)} games. Each
          factor moves this player's forecast up or down.
        </p>
        <FactorChart factors={p.factors} />
      </section>

      {p.similar.length > 0 && (
        <section className="mt-12">
          <h2 className="font-display text-2xl font-bold uppercase">Similar past comebacks</h2>
          <p className="mt-1 mb-4 text-sm text-muted">
            Players with a similar age and role who missed a season (for any reason), and how many games they played when
            they came back.
          </p>
          <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">
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

      <section className="mt-12">
        <h2 className="font-display text-2xl font-bold uppercase">Games played by season</h2>
        <div className="mt-2 mb-1 flex gap-5 text-xs text-muted">
          <span className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm bg-played" /> Played
          </span>
          <span className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm bg-accent" /> {p.comeback ? 'Forecast if healthy' : 'Forecast'}
          </span>
        </div>
        <HistoryChart
          history={p.history}
          forecast={p.shown}
          forecastSeason={meta.forecastSeason}
          forecastLabel={p.comeback ? 'Forecast if healthy' : 'Forecast'}
        />
        <p className="text-xs text-faint">
          {p.history.length} seasons since {p.history[0]?.season}.{' '}
          {p.comeback ? `Missed ${meta.dataThrough}.` : `${playedText(p.games, p.seasonGames)} in ${meta.dataThrough}.`}
        </p>
      </section>
    </article>
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

function BigText({ label, text, note }: { label: string; text: string; note?: string }) {
  return (
    <div className="bg-surface px-6 py-6">
      <div className="text-sm text-muted">{label}</div>
      <div className="mt-2 font-display text-3xl leading-tight font-bold">{text}</div>
      {note && <div className="mt-2 text-sm text-faint">{note}</div>}
    </div>
  )
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
  label: string
  note?: string
  accent?: boolean
  children?: React.ReactNode
}) {
  return (
    <div className="bg-surface px-6 py-6">
      <div className="text-sm text-muted">{label}</div>
      <div className="mt-1 flex items-baseline gap-2">
        <span className={`tabular font-display text-7xl leading-none font-extrabold ${accent ? 'text-accent' : ''}`}>{value}</span>
        <span className="text-lg text-muted">{unit}</span>
      </div>
      {note && <div className="mt-2 text-sm text-faint">{note}</div>}
      {children}
    </div>
  )
}
