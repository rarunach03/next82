import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import Availability from '../components/Availability'
import InjuredBadge from '../components/InjuredBadge'
import RosterPicker from '../components/RosterPicker'
import ScoringPicker from '../components/ScoringPicker'
import Tip from '../components/Tip'
import { GLOSSARY } from '../glossary'
import { isInjured, parseFormat, useFantasy } from '../data'
import { isHighRisk, rosterFlags, RULES, type Flag } from '../roster/flags.ts'
import { MAX_ROSTER, restValue, rosterPool, teamPosition, type RosterPlayer } from '../roster/model.ts'
import { simulate, RUNS, type Simulation } from '../roster/simulate.ts'
import { swapSuggestions } from '../roster/swaps.ts'
import { DEFAULT_SEED, loadSaved, save, type Saved } from '../roster/storage.ts'
import { parseTrade, rosterAfter, tradeParam, type Trade } from '../roster/trade.ts'
import TradePanel from '../components/TradePanel'
import type { Fantasy, FantasyFormat, Index } from '../types'

/** Build (or enter) a fantasy roster and see how its availability holds up. Saved in this browser. */
export default function MyRoster({ index }: { index: Index }) {
  const fantasy = useFantasy()
  const [saved, setSaved] = useState<Saved>(loadSaved)
  // Scoring and the trade being tested live in the URL, so a trade can be shared.
  const [params, setParams] = useSearchParams()
  const format = parseFormat(params.get('format'))
  const trade = parseTrade(params.get('trade'))
  useEffect(() => save(saved), [saved])

  const pool = useMemo(() => (fantasy === undefined ? null : rosterPool(index.players, fantasy)), [index, fantasy])
  // Saved players who left the pool (released, no forecast) are dropped from view but kept in storage.
  const roster = useMemo(() => {
    const byId = new Map((pool ?? []).map((p) => [p.id, p]))
    return saved.ids.map((id) => byId.get(id)).filter((p): p is RosterPlayer => p !== undefined)
  }, [pool, saved.ids])
  const sim = useMemo(() => simulate(roster, saved.seed), [roster, saved.seed])
  const flags = useMemo(() => rosterFlags(roster, sim, (p) => p.perGame?.[format] ?? null), [roster, sim, format])
  // The same checks for the roster as it would be after the trade.
  const tradeKey = trade ? tradeParam(trade) : null
  const after = useMemo(() => {
    const t = parseTrade(tradeKey)
    if (!t || !pool) return null
    const byId = new Map(pool.map((p) => [p.id, p]))
    const players = rosterAfter(roster.map((p) => p.id), t)
      .map((id) => byId.get(id))
      .filter((p): p is RosterPlayer => p !== undefined)
    const afterSim = simulate(players, saved.seed)
    return { players, sim: afterSim, flags: rosterFlags(players, afterSim, (p) => p.perGame?.[format] ?? null) }
  }, [tradeKey, pool, roster, saved.seed, format])
  if (!pool) return <p className="py-16 text-muted">Loading…</p>

  const missing = saved.ids.length - roster.length
  const setIds = (ids: number[]) => setSaved((s) => ({ ...s, ids }))
  const add = (p: RosterPlayer) => saved.ids.length < MAX_ROSTER && setIds([...saved.ids, p.id])
  const remove = (id: number) => setIds(saved.ids.filter((i) => i !== id))
  // A swap keeps the roster's order: the new player takes the old one's place.
  const swap = (out: number, inId: number) => setIds(saved.ids.map((i) => (i === out ? inId : i)))
  const { meta } = index
  function setParam(key: string, value: string | null) {
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        if (value === null) next.delete(key)
        else next.set(key, value)
        return next
      },
      { replace: true },
    )
  }
  const setFormat = (f: FantasyFormat) => setParam('format', f === 'espn' ? null : f)
  const setTrade = (t: Trade | null) => setParam('trade', t ? tradeParam(t) : null)

  return (
    <article className="pt-10 pb-16">
      <p className="text-sm font-semibold tracking-widest text-accent uppercase">Fantasy</p>
      <h1 className="mt-2 font-display text-5xl leading-none font-extrabold tracking-tight uppercase">My roster</h1>
      <p className="mt-4 max-w-2xl text-muted">
        Add the players on your fantasy team (up to {MAX_ROSTER}) to see how many games they're expected to play from
        here on, and how that holds up in a good or bad season. Your roster is saved in this browser.
      </p>

      <section className="mt-6">
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="font-display text-2xl font-bold uppercase">Players</h2>
          <span className="tabular text-sm text-muted">
            {roster.length} of {MAX_ROSTER}
          </span>
        </div>
        <div className="mt-3">
          <RosterPicker pool={pool} taken={new Set(saved.ids)} full={saved.ids.length >= MAX_ROSTER} onAdd={add} />
        </div>
        {missing > 0 && (
          <p className="mt-2 text-xs text-faint">
            {missing === 1 ? '1 saved player is' : `${missing} saved players are`} no longer on an NBA roster with a
            forecast, so {missing === 1 ? "that player isn't" : "they're not"} shown.{' '}
            <button onClick={() => setIds(roster.map((p) => p.id))} className="text-muted underline-offset-2 hover:underline">
              Remove
            </button>
          </p>
        )}
        {roster.length === 0 ? (
          <p className="mt-4 rounded-2xl border border-dashed border-line px-5 py-8 text-center text-sm text-faint">
            No players yet. Search above to add your first one.
          </p>
        ) : (
          <>
            {fantasy && (
              <div className="mt-4">
                <ScoringPicker format={format} onChange={setFormat} />
              </div>
            )}
            <RosterTable
              roster={roster}
              onRemove={remove}
              safeLow={meta.tierSafeLow}
              riskyLow={meta.setbackGames}
              fantasy={fantasy ?? null}
              format={format}
            />
          </>
        )}
        {!trade && fantasy && (
          <button
            onClick={() => setTrade({ give: [], get: [] })}
            className="mt-3 rounded-lg border border-line px-3 py-2 text-sm font-medium text-muted transition hover:border-accent hover:text-accent"
          >
            Test a trade
          </button>
        )}
      </section>

      {trade && fantasy && after && (
        <TradePanel
          trade={trade}
          onChange={setTrade}
          onApply={() => {
            setIds(after.players.map((p) => p.id))
            setTrade(null)
          }}
          roster={roster}
          pool={pool}
          fantasy={fantasy}
          format={format}
          before={{ sim, flags }}
          after={after}
        />
      )}

      {roster.length > 0 && <Flags flags={flags} />}

      {roster.length > 0 && (
        <SeasonOutlook sim={sim} size={roster.length} onSeed={(seed) => setSaved((s) => ({ ...s, seed }))} />
      )}

      {roster.some(isHighRisk) && (
        <Swaps roster={roster} pool={pool} onSwap={swap} safeLow={meta.tierSafeLow} riskyLow={meta.setbackGames} />
      )}

      <p className="mt-8 text-xs text-faint">
        Next82 forecasts availability: how many games each player will play. Value multiplies that by production per
        game from the{' '}
        <Link to="/rankings" className="text-muted underline-offset-2 hover:underline">
          fantasy rankings
        </Link>{' '}
        (this season blended with the last three); it doesn't forecast changes in a player's role or form. The simulation
        treats players as independent, so it doesn't capture a whole team resting stars late in the season.
      </p>
    </article>
  )
}

function RosterTable({
  roster,
  onRemove,
  safeLow,
  riskyLow,
  fantasy,
  format,
}: {
  roster: RosterPlayer[]
  onRemove: (id: number) => void
  safeLow: number
  riskyLow: number
  fantasy: Fantasy | null
  format: FantasyFormat
}) {
  const value = (p: RosterPlayer) => (fantasy ? restValue(p, format, fantasy.replacement[format]) : null)
  const values = roster.map(value)
  const total = values.reduce<number>((s, v) => s + (v ?? 0), 0)
  const fmtValue = (v: number | null) => (v === null ? '–' : Math.round(v).toLocaleString('en-US'))
  return (
    <div className="mt-4 overflow-x-auto rounded-2xl border border-line bg-surface">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs tracking-wide text-faint">
            <th className="py-3 pr-2 pl-3 font-medium uppercase sm:pl-4">Player</th>
            <th className="py-3 pr-2 font-medium whitespace-nowrap uppercase sm:pr-3">
              <Tip tip="Games played so far, and the updated forecast of games still to come, out of the team's games left.">
                Games
              </Tip>
            </th>
            <th className="hidden py-3 pr-2 font-medium whitespace-nowrap uppercase sm:table-cell sm:pr-3">
              <Tip tip={GLOSSARY.likelyRange}>Likely left</Tip>
            </th>
            <th className="hidden py-3 pr-2 font-medium uppercase sm:table-cell sm:pr-3">
              <Tip tip={GLOSSARY.tier(safeLow, riskyLow)}>Availability</Tip>
            </th>
            {fantasy && (
              <th className="hidden py-3 pr-2 text-right font-medium uppercase sm:table-cell sm:pr-3">
                <Tip tip={`Production per game above a free-agent pickup, times games expected from here on. ${GLOSSARY.aboveReplacement(fantasy.poolSize)}`}>
                  Value
                </Tip>
              </th>
            )}
            <th className="w-10 py-3 pr-3 sm:pr-4">
              <span className="sr-only">Remove</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {roster.map((p, i) => (
            <tr key={p.id} className="border-b border-line/60 last:border-0">
              <td className="py-3 pr-2 pl-3 sm:pl-4">
                {p.rookie ? (
                  <span className="font-medium">{p.name}</span>
                ) : (
                  <Link to={`/player/${p.id}`} className="font-medium hover:text-accent">
                    {p.name}
                  </Link>
                )}
                <span className="ml-2 text-xs text-faint">{teamPosition(p)}</span>
                {isInjured(p) && (
                  <span className="ml-2 hidden sm:inline">
                    <InjuredBadge p={p} />
                  </span>
                )}
                {/* Phones: status, availability and range under the name, so games fit. */}
                <div className="mt-1 flex flex-wrap items-center gap-1.5 sm:hidden">
                  {isInjured(p) && <InjuredBadge p={p} />}
                  <Availability tier={p.tier} reason={p.noTierReason} safeLow={safeLow} riskyLow={riskyLow} />
                  {p.restLow !== null && p.restHigh !== null && (
                    <span className="tabular text-xs text-faint">
                      likely {Math.round(p.restLow)}–{Math.round(p.restHigh)} left
                    </span>
                  )}
                </div>
              </td>
              <td className="tabular py-3 pr-2 whitespace-nowrap sm:pr-3">
                <span className="font-semibold">{Math.round(p.rest)}</span>
                <span className="text-faint"> of {p.gamesLeft} left</span>
                <div className="text-xs text-faint">{p.playedSoFar} played</div>
                {fantasy && <div className="text-xs text-muted sm:hidden">value {fmtValue(values[i])}</div>}
              </td>
              <td className="tabular hidden py-3 pr-2 whitespace-nowrap text-muted sm:table-cell sm:pr-3">
                {p.restLow !== null && p.restHigh !== null ? `${Math.round(p.restLow)}–${Math.round(p.restHigh)}` : '–'}
              </td>
              <td className="hidden py-3 pr-2 sm:table-cell sm:pr-3">
                <Availability tier={p.tier} reason={p.noTierReason} safeLow={safeLow} riskyLow={riskyLow} />
              </td>
              {fantasy && <td className="tabular hidden py-3 pr-2 text-right font-semibold sm:table-cell sm:pr-3">{fmtValue(values[i])}</td>}
              <td className="py-3 pr-3 text-right sm:pr-4">
                <button
                  onClick={() => onRemove(p.id)}
                  aria-label={`Remove ${p.name}`}
                  className="rounded-md px-2 py-1 text-muted transition hover:bg-surface-2 hover:text-ink"
                >
                  ✕
                </button>
              </td>
            </tr>
          ))}
        </tbody>
        {fantasy && (
          <tfoot>
            <tr className="border-t border-line text-sm">
              <td className="py-3 pr-2 pl-3 text-muted sm:pl-4">
                Roster value<span className="text-faint"> (rest of season)</span>
              </td>
              <td className="tabular py-3 pr-2 font-semibold sm:hidden">{fmtValue(total)}</td>
              {/* Desktop: under games, likely left and availability. */}
              <td className="hidden sm:table-cell" colSpan={3} />
              <td className="tabular hidden py-3 pr-2 text-right font-semibold sm:table-cell sm:pr-3">{fmtValue(total)}</td>
              <td />
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  )
}

const pct = (games: number, max: number) => (max > 0 ? `${Math.round((games / max) * 100)}%` : '–')
const whole = (v: number) => Math.round(v).toLocaleString('en-US')

/** Team totals and the simulated rest of the season: bad, typical and good outcomes. */
function SeasonOutlook({ sim, size, onSeed }: { sim: Simulation; size: number; onSeed: (seed: number) => void }) {
  return (
    <section className="mt-8">
      <h2 className="font-display text-2xl font-bold uppercase">Rest of the season</h2>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <Stat
          label="Expected games left"
          value={whole(sim.mean)}
          note={`of ${whole(sim.maxRest)} possible (${pct(sim.mean, sim.maxRest)})`}
          tip={`The average across the simulated seasons below, for your ${size} players. Possible: every team game left for every player.`}
        />
        <Stat
          label="Season total"
          value={whole(sim.played + sim.mean)}
          note={`${whole(sim.played)} played so far + expected games left`}
        />
      </div>
      {sim.forecastSum - sim.mean >= 1 && (
        <p className="mt-2 text-xs text-faint">
          Adding up each player's forecast gives {whole(sim.forecastSum)}. Each forecast is a player's middle outcome, and
          an injury takes away more games than good luck can add, so the roster's expected total is lower.
        </p>
      )}

      <div className="mt-4 rounded-2xl border border-line bg-surface p-4 sm:p-5">
        <h3 className="font-semibold">If the season played out {RUNS.toLocaleString('en-US')} times</h3>
        <p className="mt-1 text-sm text-muted">
          Each simulated season draws every player's games from their likely range, then adds up the roster.
        </p>
        <div className="mt-4 grid grid-cols-3 gap-2 text-center">
          <Outcome label="Bad season" sub="1 in 10 are worse" games={sim.low} max={sim.maxRest} />
          <Outcome label="Typical" sub="the middle outcome" games={sim.median} max={sim.maxRest} accent />
          <Outcome label="Good season" sub="1 in 10 are better" games={sim.high} max={sim.maxRest} />
        </div>
        <Histogram sim={sim} />
        <SeedControl seed={sim.seed} onSeed={onSeed} />
      </div>
    </section>
  )
}

function Stat({ label, value, note, tip }: { label: string; value: string; note: string; tip?: string }) {
  return (
    <div className="rounded-2xl border border-line bg-surface px-4 py-4">
      <div className="text-sm text-muted">{tip ? <Tip tip={tip}>{label}</Tip> : label}</div>
      <div className="tabular mt-1 font-display text-4xl font-bold">{value}</div>
      <div className="mt-1 text-xs text-faint">{note}</div>
    </div>
  )
}

function Outcome({ label, sub, games, max, accent = false }: { label: string; sub: string; games: number; max: number; accent?: boolean }) {
  return (
    <div className="rounded-xl bg-surface-2 px-2 py-3">
      <div className="text-xs font-medium text-muted">{label}</div>
      <div className={`tabular mt-1 font-display text-3xl font-bold ${accent ? 'text-accent' : ''}`}>{whole(games)}</div>
      <div className="tabular text-xs text-muted">{pct(games, max)} of possible</div>
      <div className="mt-0.5 hidden text-[11px] text-faint sm:block">{sub}</div>
    </div>
  )
}

/** Simulated roster games left, binned. The bar holding the typical outcome is highlighted. */
function Histogram({ sim }: { sim: Simulation }) {
  const [hover, setHover] = useState<number | null>(null)
  const top = Math.max(...sim.bins.map((b) => b.count), 1)
  const label = (b: { from: number; to: number }) => (b.from === b.to ? whole(b.from) : `${whole(b.from)}–${whole(b.to)}`)
  const shown = hover !== null ? sim.bins[hover] : null
  if (sim.bins.length < 2) return null
  return (
    <figure className="mt-5">
      <figcaption className="flex justify-between gap-3 text-xs text-faint">
        <span>Simulated seasons by roster games left</span>
        <span className="tabular text-muted" aria-live="polite">
          {shown ? `${label(shown)} games: ${pct(shown.count, sim.runs)} of seasons` : ''}
        </span>
      </figcaption>
      <div className="mt-2 flex h-28 items-end gap-0.5" onPointerLeave={() => setHover(null)}>
        {sim.bins.map((b, i) => {
          const typical = b.from <= sim.median && sim.median <= b.to
          return (
            <div
              key={b.from}
              role="img"
              aria-label={`${label(b)} games: ${pct(b.count, sim.runs)} of simulated seasons`}
              onPointerEnter={() => setHover(i)}
              className="flex h-full flex-1 items-end"
            >
              <div
                className={`w-full rounded-t ${typical ? 'bg-accent' : hover === i ? 'bg-ink/50' : 'bg-ink/25'}`}
                style={{ height: `${(b.count / top) * 100}%`, minHeight: b.count ? 2 : 0 }}
              />
            </div>
          )
        })}
      </div>
      <div className="tabular mt-1 flex justify-between border-t border-line pt-1 text-xs text-faint">
        <span>{whole(sim.bins[0].from)}</span>
        <span>{whole(sim.bins[sim.bins.length - 1].to)} games</span>
      </div>
    </figure>
  )
}

/** The simulation's seed: the same seed and roster always give the same numbers. */
function SeedControl({ seed, onSeed }: { seed: number; onSeed: (seed: number) => void }) {
  return (
    <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-faint">
      <label className="flex items-center gap-2">
        <Tip tip="The simulation uses this seed, so the same roster always shows the same numbers. Change it to see how much they move from one set of simulations to another.">
          Seed
        </Tip>
        <input
          type="number"
          inputMode="numeric"
          value={seed}
          onChange={(e) => {
            const v = Number.parseInt(e.target.value, 10)
            if (Number.isInteger(v) && v >= 0) onSeed(v)
          }}
          className="tabular w-24 rounded-md border border-line bg-surface-2 px-2 py-1 text-sm text-ink outline-none focus:border-accent"
        />
      </label>
      <button
        onClick={() => onSeed(Math.floor(Math.random() * 1_000_000))}
        className="rounded-md border border-line px-2 py-1 text-muted transition hover:text-ink"
      >
        New seed
      </button>
      {seed !== DEFAULT_SEED && (
        <button onClick={() => onSeed(DEFAULT_SEED)} className="rounded-md px-2 py-1 text-muted transition hover:text-ink">
          Reset to {DEFAULT_SEED}
        </button>
      )}
    </div>
  )
}

/** Plain-English warnings (rules in roster/flags.ts), or a short all-clear. */
function Flags({ flags }: { flags: Flag[] }) {
  return (
    <section className="mt-8">
      <h2 className="font-display text-2xl font-bold uppercase">Risk check</h2>
      {flags.length === 0 ? (
        <p className="mt-3 rounded-2xl border border-line bg-surface px-4 py-3 text-sm text-muted">
          <span className="font-semibold text-safe">No red flags.</span> Your top players aren't high-risk, no more than one
          player is injured, and even a bad season keeps {Math.round(RULES.badSeasonShareMax * 100)}%+ of possible games.
        </p>
      ) : (
        <ul className="mt-3 space-y-2">
          {flags.map((f) => (
            <li key={f.id} className="flex gap-3 rounded-2xl border border-moderate/40 bg-moderate/5 px-4 py-3 text-sm">
              <span aria-hidden className="font-bold text-moderate">!</span>
              <span>
                <span className="sr-only">Warning: </span>
                {f.text}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

/** For each high-risk player: up to three similar players per game with a safer forecast. */
function Swaps({
  roster,
  pool,
  onSwap,
  safeLow,
  riskyLow,
}: {
  roster: RosterPlayer[]
  pool: RosterPlayer[]
  onSwap: (out: number, inId: number) => void
  safeLow: number
  riskyLow: number
}) {
  const taken = new Set(roster.map((p) => p.id))
  return (
    <section className="mt-8">
      <h2 className="font-display text-2xl font-bold uppercase">Safer swaps</h2>
      <p className="mt-1 max-w-2xl text-sm text-muted">
        For each high-risk player: players with similar production per game (minutes, points, rebounds, assists,
        steals, blocks, threes and turnovers) at a shared position, in a safer tier and expected to play more games.
      </p>
      <div className="mt-3 space-y-3">
        {roster.filter(isHighRisk).map((p) => {
          const swaps = swapSuggestions(p, pool, taken)
          return (
            <div key={p.id} className="rounded-2xl border border-line bg-surface p-4">
              <div className="text-sm">
                Instead of <span className="font-semibold">{p.name}</span>{' '}
                <span className="tabular text-faint">
                  ({Math.round(p.rest)} of {p.gamesLeft} games left)
                </span>
              </div>
              {swaps.length === 0 ? (
                <p className="mt-2 text-sm text-faint">No similar player with a safer forecast.</p>
              ) : (
                <ul className="mt-2 divide-y divide-line">
                  {swaps.map(({ player: c }) => (
                    <li key={c.id} className="flex items-center justify-between gap-3 py-2.5">
                      <div className="min-w-0">
                        <div className="truncate">
                          <Link to={`/player/${c.id}`} className="font-medium hover:text-accent">
                            {c.name}
                          </Link>
                          <span className="ml-2 text-xs text-faint">{teamPosition(c)}</span>
                        </div>
                        <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
                          <Availability tier={c.tier} reason={c.noTierReason} safeLow={safeLow} riskyLow={riskyLow} />
                          <span className="tabular">
                            {Math.round(c.rest)} of {c.gamesLeft} left
                          </span>
                          {c.stats?.PTS != null && (
                            <span className="tabular text-faint">
                              {c.stats.PTS} pts · {c.stats.REB} reb · {c.stats.AST} ast
                            </span>
                          )}
                        </div>
                      </div>
                      <button
                        onClick={() => onSwap(p.id, c.id)}
                        aria-label={`Swap ${c.name} in for ${p.name}`}
                        className="shrink-0 rounded-lg border border-line px-3 py-1.5 text-sm font-medium text-muted transition hover:border-accent hover:text-accent"
                      >
                        Swap in
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}

