import { useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import InjuredBadge from '../components/InjuredBadge'
import Availability from '../components/Availability'
import Tip from '../components/Tip'
import { GLOSSARY } from '../glossary'
import { fantasyValue, isInjured, shortDate, useFantasy } from '../data'
import type { FantasyFormat, FantasyPlayer, Meta, Team, Tier } from '../types'

const FORMATS: { id: FantasyFormat; label: string }[] = [
  { id: 'espn', label: 'ESPN points' },
  { id: 'yahoo', label: 'Yahoo points' },
  { id: 'cat9', label: '9-cat' },
]
type View = 'ros' | 'full'
type SortKey = 'value' | 'perGame' | 'games' | 'change' | 'discount' | 'name'

interface Row {
  p: FantasyPlayer
  perGame: number
  games: number
  value: number
  /** Value lost compared with playing every game (only for players worth rostering per game). */
  discount: number
  perGameRank: number
  valueRank: number
}

/** Rank by a value, highest first: 1, 2, 3... */
function ranks(rows: Row[], key: (r: Row) => number): Map<number, number> {
  return new Map([...rows].sort((a, b) => key(b) - key(a)).map((r, i) => [r.p.id, i + 1]))
}

export default function Rankings({ meta, teams }: { meta: Meta; teams: Team[] }) {
  const fantasy = useFantasy()
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const format = (params.get('format') as FantasyFormat) || 'espn'
  const view = (params.get('view') as View) || 'ros'
  const team = params.get('team') ?? ''
  const tier = params.get('tier') ?? ''
  const more = params.get('cols') === 'more'
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: 'value', desc: true })

  // Update from the latest URL (not this render's copy), so quick successive changes
  // to different controls don't overwrite each other.
  function set(key: string, value: string, fallback: string) {
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        if (value === fallback) next.delete(key)
        else next.set(key, value)
        return next
      },
      { replace: true },
    )
  }

  // Ranks are computed over every player, so filtering never changes a player's rank.
  const allRows = useMemo<Row[]>(() => {
    if (!fantasy) return []
    // Value above replacement (the 156th-best player per game), so more games never
    // lowers the value of a player worth rostering. Same formulas as next82.fantasy.
    const replacement = fantasy.replacement[format]
    const rows = fantasy.players.map((p) => {
      const perGame = p.perGame[format]
      const above = perGame - replacement
      const games = view === 'ros' ? p.restGames : p.seasonGames
      const missed = view === 'ros' ? p.gamesLeft - p.restGames : 82 - p.seasonGames
      return { p, perGame, games, value: fantasyValue(perGame, replacement, games), discount: Math.max(above, 0) * missed, perGameRank: 0, valueRank: 0 }
    })
    const byPerGame = ranks(rows, (r) => r.perGame)
    const byValue = ranks(rows, (r) => r.value)
    return rows.map((r) => ({ ...r, perGameRank: byPerGame.get(r.p.id)!, valueRank: byValue.get(r.p.id)! }))
  }, [fantasy, format, view])

  const rows = useMemo(() => {
    const filtered = allRows.filter(
      (r) =>
        (!team || r.p.team === team) &&
        (!tier ||
          (tier === 'rookie' ? r.p.rookie : tier === 'none' ? !r.p.tier && !r.p.rookie : r.p.tier === (tier as Tier))),
    )
    const key: Record<SortKey, (r: Row) => number | string> = {
      value: (r) => r.value,
      perGame: (r) => r.perGame,
      games: (r) => r.games,
      change: (r) => r.perGameRank - r.valueRank,
      discount: (r) => r.discount,
      name: (r) => r.p.name,
    }
    const k = key[sort.key]
    return [...filtered].sort((a, b) => {
      const x = k(a)
      const y = k(b)
      const cmp = typeof x === 'string' ? x.localeCompare(y as string) : (x as number) - (y as number)
      return sort.desc ? -cmp : cmp
    })
  }, [allRows, team, tier, sort])

  if (fantasy === undefined) return <p className="py-16 text-muted">Loading rankings…</p>
  if (fantasy === null) return <p className="py-16 text-muted">Fantasy rankings aren't available yet.</p>

  const cat9 = format === 'cat9'
  const fmt = (v: number, digits: number) => v.toLocaleString('en-US', { maximumFractionDigits: digits, minimumFractionDigits: digits })
  const header = (key: SortKey, label: React.ReactNode, tip?: string) => (
    <th className="py-3 pr-2 sm:pr-3 font-medium whitespace-nowrap">
      <button
        onClick={() => setSort((s) => ({ key, desc: s.key === key ? !s.desc : key !== 'name' }))}
        className={`uppercase transition hover:text-ink ${sort.key === key ? 'text-ink' : ''}`}
      >
        {label}
        {sort.key === key && <span aria-hidden> {sort.desc ? '↓' : '↑'}</span>}
      </button>
      {tip && <Info tip={tip} />}
    </th>
  )

  return (
    <article className="pt-10 pb-16">
      <p className="text-sm font-semibold tracking-widest text-accent uppercase">Fantasy</p>
      <h1 className="mt-2 font-display text-5xl leading-none font-extrabold tracking-tight uppercase">Rankings</h1>
      {meta.updatedAsOf && (
        <p className="mt-2 text-sm text-faint">Updated through {shortDate(meta.updatedAsOf)}</p>
      )}
      <p className="mt-4 max-w-2xl text-muted">
        Who's worth the most {view === 'ros' ? 'from here on' : 'this season'}: production per game{' '}
        <Tip tip={GLOSSARY.aboveReplacement(fantasy.poolSize)}>above a free-agent pickup</Tip>, times the games each
        player is expected to play. Players expected to miss games rank lower.
      </p>

      <div className="mt-6 flex flex-wrap items-end gap-3">
        <Segmented
          label={
            <>
              Scoring (<Tip tip={GLOSSARY.cat9}>what's 9-cat?</Tip>)
            </>
          }
          options={FORMATS.map((f) => ({ value: f.id, label: f.label }))}
          value={format}
          onChange={(v) => set('format', v, 'espn')}
        />
        <Segmented
          label="View"
          options={[
            { value: 'ros', label: 'Rest of season' },
            { value: 'full', label: 'Full season' },
          ]}
          value={view}
          onChange={(v) => set('view', v, 'ros')}
        />
        <Select label="Team" value={team} onChange={(v) => set('team', v, '')}>
          <option value="">All teams</option>
          {teams.map((t) => (
            <option key={t.abbr} value={t.abbr}>
              {t.name}
            </option>
          ))}
        </Select>
        <Select label={<Tip tip={GLOSSARY.tier(meta.tierSafeLow, meta.setbackGames)}>Availability tier</Tip>} value={tier} onChange={(v) => set('tier', v, '')}>
          <option value="">All</option>
          <option value="Safe">Safe</option>
          <option value="Moderate">Moderate</option>
          <option value="Risky">Risky</option>
          <option value="none">No tier</option>
          <option value="rookie">Rookies</option>
        </Select>
        <button
          onClick={() => set('cols', more ? '' : 'more', '')}
          aria-pressed={more}
          className={`rounded-lg border px-3 py-2 text-sm font-medium transition ${more ? 'border-accent text-accent' : 'border-line text-muted hover:text-ink'}`}
        >
          {more ? 'Fewer columns' : 'More columns'}
        </button>
      </div>

      <div className="mt-5 overflow-x-auto rounded-2xl border border-line bg-surface">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs tracking-wide text-faint">
              <th className="w-10 py-3 pr-2 pl-3 sm:w-12 sm:pl-4 font-medium uppercase">Rank</th>
              {header('name', 'Player')}
              <th className="hidden py-3 pr-2 sm:pr-3 font-medium whitespace-nowrap uppercase sm:table-cell">
                Status
                <Info tip="Injured: listed Out with an injury or with a known return timeline (hover the badge for the source). Missing games: out 5+ straight games without being on the injury report." />
              </th>
              <th className="hidden py-3 pr-2 sm:pr-3 font-medium whitespace-nowrap uppercase sm:table-cell">
                Availability
                <Info tip={GLOSSARY.tier(meta.tierSafeLow, meta.setbackGames)} />
              </th>
              {header(
                'games',
                <>
                  Games<span className="hidden sm:inline">{view === 'ros' ? ' left' : ' this season'}</span>
                </>,
              )}
              {header('value', 'Value', GLOSSARY.aboveReplacement(fantasy.poolSize))}
              {more && (
                <>
                  {header('perGame', cat9 ? 'Per game (z)' : 'Per game')}
                  <th className="py-3 pr-2 sm:pr-3 font-medium whitespace-nowrap uppercase">
                    Per-game rank
                    <Info tip={GLOSSARY.perGameRank} />
                  </th>
                  {header('change', 'Rank change', GLOSSARY.rankChange)}
                  {header('discount', 'Durability discount', GLOSSARY.durability)}
                  <th className="py-3 pr-2 sm:pr-3 font-medium whitespace-nowrap uppercase">
                    Likely games
                    <Info tip={GLOSSARY.likelyRange} />
                  </th>
                  <th className="py-3 pr-4 font-medium whitespace-nowrap uppercase">
                    Back-to-back rest
                    <Info tip={GLOSSARY.b2b} />
                  </th>
                </>
              )}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const change = r.perGameRank - r.valueRank
              return (
                <tr
                  key={r.p.id}
                  // Rookies have no player page yet (no preseason forecast).
                  onClick={r.p.rookie ? undefined : () => navigate(`/player/${r.p.id}`)}
                  className={`border-b border-line/60 transition last:border-0 ${r.p.rookie ? '' : 'cursor-pointer hover:bg-surface-2'}`}
                >
                  <td className="tabular py-3 pr-2 pl-3 sm:pl-4 font-display text-lg font-bold">{r.valueRank}</td>
                  <td className="py-3 pr-2 sm:pr-3">
                    <span className="font-medium">{r.p.name}</span>
                    <span className="ml-2 text-xs text-faint">{r.p.team}</span>
                    {/* Phones: status and availability under the name, so games and value fit. */}
                    <div className="mt-1 flex flex-wrap items-center gap-1.5 sm:hidden">
                      {isInjured(r.p) && <InjuredBadge p={r.p} />}
                      <Availability tier={r.p.tier} reason={r.p.noTierReason} safeLow={meta.tierSafeLow} riskyLow={meta.setbackGames} />
                    </div>
                  </td>
                  <td className="hidden py-3 pr-2 sm:pr-3 sm:table-cell">
                    {isInjured(r.p) ? (
                      <InjuredBadge p={r.p} />
                    ) : r.p.out ? (
                      <span className="text-xs text-muted">Missing games</span>
                    ) : (
                      <span className="text-xs text-faint">Active</span>
                    )}
                  </td>
                  <td className="hidden py-3 pr-2 sm:pr-3 sm:table-cell">
                    <Availability tier={r.p.tier} reason={r.p.noTierReason} safeLow={meta.tierSafeLow} riskyLow={meta.setbackGames} />
                  </td>
                  <td className="tabular py-3 pr-2 sm:pr-3 text-muted">
                    {r.p.override && !r.p.override.latestReturn ? (
                      <Tip tip="No firm return date, so this uses the middle of the likely range.">~{Math.round(r.games)}</Tip>
                    ) : (
                      Math.round(r.games)
                    )}
                    {view === 'ros' && <span className="hidden text-faint sm:inline"> of {r.p.gamesLeft}</span>}
                  </td>
                  <td className="tabular py-3 pr-2 sm:pr-3 font-semibold">{fmt(r.value, 0)}</td>
                  {more && (
                    <>
                      <td className="tabular py-3 pr-2 sm:pr-3">{fmt(r.perGame, cat9 ? 2 : 1)}</td>
                      <td className="tabular py-3 pr-2 sm:pr-3 text-muted">{r.perGameRank}</td>
                      <td className="tabular py-3 pr-2 sm:pr-3">
                        {change === 0 ? (
                          <span className="text-faint">–</span>
                        ) : (
                          <span className={change > 0 ? 'text-up' : 'text-down'}>
                            {change > 0 ? '▲' : '▼'} {Math.abs(change)}
                          </span>
                        )}
                      </td>
                      <td className="tabular py-3 pr-2 sm:pr-3 text-muted">{r.discount > 0 ? `−${fmt(r.discount, 0)}` : '–'}</td>
                      <td className="tabular py-3 pr-2 sm:pr-3 whitespace-nowrap text-muted">
                        {r.p.restLow !== null && r.p.restHigh !== null && view === 'ros'
                          ? `${Math.round(r.p.restLow)}–${Math.round(r.p.restHigh)}`
                          : '–'}
                      </td>
                      <td className="tabular py-3 pr-4 whitespace-nowrap text-muted">
                        {r.p.b2bRate !== null && r.p.b2bLeft !== null ? (
                          <>
                            {Math.round(r.p.b2bRate * 100)}%<span className="text-faint"> of {r.p.b2bLeft}</span>
                          </>
                        ) : (
                          '–'
                        )}
                      </td>
                    </>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <details className="mt-4 text-xs text-faint">
        <summary className="cursor-pointer text-sm text-muted hover:text-ink">How these rankings are calculated</summary>
        <div className="mt-2 space-y-1">
          <p>
            Value = (per-game score − the {fantasy.poolSize}th-best player's per-game score) × games{' '}
            {view === 'ros' ? 'expected from here on' : 'expected this season'}. This season's stats are blended with the
            last three seasons, weighted like {fantasy.shrinkGames} extra games, so a hot start doesn't take over. ESPN and
            Yahoo use each site's default points scoring. 9-cat values are z-scores per game against the top{' '}
            {fantasy.poolSize} players (12 teams × 13), with FG% and FT% weighted by attempts.
          </p>
          <p>
            Injured players with no firm return date use the middle of their likely range (marked ~). Durability discount:
            value lost compared with playing {view === 'ros' ? 'every remaining game' : 'all 82 games'}. Back-to-back rest
            comes from the last three seasons, pulled toward the league average; the forecasts already count typical resting.
          </p>
          <p>
            Rookies are ranked once they've played {fantasy.rookieMinGames} games: their stats are blended with past rookies
            from the same draft range
            {fantasy.rookieShrinkGames !== null && <> (weighted like {fantasy.rookieShrinkGames} extra games)</>}. Not
            ranked: players not on a roster who haven't played this season.
          </p>
        </div>
      </details>
    </article>
  )
}

function Segmented({
  label,
  options,
  value,
  onChange,
}: {
  label: React.ReactNode
  options: { value: string; label: string }[]
  value: string
  onChange: (v: string) => void
}) {
  return (
    <div role="radiogroup" aria-label={typeof label === 'string' ? label : 'Scoring'}>
      <div className="mb-1 text-xs text-faint">{label}</div>
      <div className="flex rounded-lg border border-line bg-surface p-0.5">
        {options.map((o) => (
          <button
            key={o.value}
            role="radio"
            aria-checked={value === o.value}
            onClick={() => onChange(o.value)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
              value === o.value ? 'bg-accent text-bg' : 'text-muted hover:text-ink'
            }`}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  )
}

function Select({ label, value, onChange, children }: { label: React.ReactNode; value: string; onChange: (v: string) => void; children: React.ReactNode }) {
  return (
    <label>
      <div className="mb-1 text-xs text-faint">{label}</div>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-accent"
      >
        {children}
      </select>
    </label>
  )
}

/** A small ⓘ beside a column heading that explains it on hover or tap. */
function Info({ tip }: { tip: string }) {
  return (
    <Tip tip={tip} className="ml-1 cursor-help align-middle text-[11px] text-faint normal-case hover:text-ink">
      <span aria-label="What's this?">ⓘ</span>
    </Tip>
  )
}
