import { useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import TierPill from '../components/TierPill'
import { shortDate, useFantasy } from '../data'
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
      return { p, perGame, games, value: above * games, discount: Math.max(above, 0) * missed, perGameRank: 0, valueRank: 0 }
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
  const header = (key: SortKey, label: string, className = '') => (
    <th className={`py-3 pr-3 font-medium ${className}`}>
      <button
        onClick={() => setSort((s) => ({ key, desc: s.key === key ? !s.desc : key !== 'name' }))}
        className={`uppercase transition hover:text-ink ${sort.key === key ? 'text-ink' : ''}`}
      >
        {label}
        {sort.key === key && <span aria-hidden> {sort.desc ? '↓' : '↑'}</span>}
      </button>
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
        {view === 'ros' ? 'Rest-of-season' : 'Full-season'} value is per-game production above replacement level (the{' '}
        {fantasy.poolSize}th-best player per game, roughly the best free agent) times the games each player is forecast
        to play{view === 'ros' ? ' from here on' : ' this season'}. Players who miss games drop below their per-game
        rank. This season's stats are blended with the last three seasons, weighted like{' '}
        {fantasy.shrinkGames} extra games, so a hot start doesn't take over.
      </p>

      <div className="mt-6 flex flex-wrap items-end gap-3">
        <Segmented
          label="Scoring"
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
        <Select label="Availability tier" value={tier} onChange={(v) => set('tier', v, '')}>
          <option value="">All</option>
          <option value="Safe">Safe</option>
          <option value="Moderate">Moderate</option>
          <option value="Risky">Risky</option>
          <option value="none">No tier</option>
          <option value="rookie">Rookies</option>
        </Select>
      </div>

      <div className="mt-5 overflow-x-auto rounded-2xl border border-line bg-surface">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs tracking-wide text-faint">
              <th className="w-16 py-3 pr-3 pl-4 font-medium uppercase">Rank</th>
              {header('name', 'Player')}
              {header('perGame', cat9 ? 'Per game (z)' : 'Per game')}
              <th className="hidden py-3 pr-3 font-medium uppercase md:table-cell">Per-game rank</th>
              {header('games', view === 'ros' ? 'Games left' : 'Season games', 'hidden sm:table-cell')}
              {header('value', view === 'ros' ? 'Rest-of-season value' : 'Season value')}
              {header('change', 'Rank change', 'hidden md:table-cell')}
              {header('discount', 'Durability discount', 'hidden lg:table-cell')}
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
                  <td className="tabular py-3 pl-4 font-display text-lg font-bold">{r.valueRank}</td>
                  <td className="py-3 pr-3">
                    <span className="font-medium">{r.p.name}</span>
                    <span className="ml-2 text-xs text-faint">{r.p.team}</span>
                    {r.p.tier && (
                      <span className="ml-2 hidden align-middle sm:inline">
                        <TierPill tier={r.p.tier} safeLow={meta.tierSafeLow} riskyLow={meta.setbackGames} />
                      </span>
                    )}
                    {r.p.override && (
                      <a
                        href={r.p.override.sourceUrl}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        title={`Manual adjustment: ${r.p.override.note}`}
                        className="ml-2 inline-flex rounded-full border border-risky/50 px-2 py-0.5 align-middle text-xs font-semibold text-risky"
                      >
                        {r.p.override.indefinite ? 'Out indefinitely' : 'Out'}
                      </a>
                    )}
                    {r.p.rookie && (
                      <span
                        title={`Rookie (${r.p.draftRange}): this season's stats blended with past rookies from the same draft range`}
                        className="ml-2 inline-flex rounded-full border border-line px-2 py-0.5 align-middle text-xs font-semibold text-muted"
                      >
                        Rookie
                      </span>
                    )}
                  </td>
                  <td className="tabular py-3 pr-3">{fmt(r.perGame, cat9 ? 2 : 1)}</td>
                  <td className="tabular hidden py-3 pr-3 text-muted md:table-cell">{r.perGameRank}</td>
                  <td className="tabular hidden py-3 pr-3 text-muted sm:table-cell">
                    <span title={r.p.override?.indefinite ? 'Out indefinitely: uses the middle of the likely range' : undefined}>
                      {r.p.override?.indefinite && '~'}
                      {Math.round(r.games)}
                    </span>
                    {view === 'ros' && <span className="text-faint"> of {r.p.gamesLeft}</span>}
                  </td>
                  <td className="tabular py-3 pr-3 font-semibold">{fmt(r.value, 0)}</td>
                  <td className="tabular hidden py-3 pr-3 md:table-cell">
                    {change === 0 ? (
                      <span className="text-faint">–</span>
                    ) : (
                      <span className={change > 0 ? 'text-up' : 'text-down'}>
                        {change > 0 ? '▲' : '▼'} {Math.abs(change)}
                      </span>
                    )}
                  </td>
                  <td className="tabular hidden py-3 pr-3 text-muted lg:table-cell">
                    {r.discount > 0 ? `−${fmt(r.discount, 0)}` : '–'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-4 space-y-1 text-xs text-faint">
        <p>
          "Out indefinitely" and "Out" mark manual adjustments from injury news (hover for the note, click for the
          source); with no return date, games use the middle of the likely range. Rank change: per-game rank minus value
          rank. ▲ means the player's availability lifts them above their per-game
          rank; ▼ means expected missed games pull them down. Durability discount: value lost compared with playing{' '}
          {view === 'ros' ? 'every remaining game' : 'all 82 games'}.
        </p>
        <p>
          ESPN and Yahoo use each site's default points scoring. 9-cat values are z-scores per game against the top{' '}
          {fantasy.poolSize} players (12 teams × 13), with FG% and FT% weighted by attempts.
        </p>
        <p>
          Rookies are ranked once they've played {fantasy.rookieMinGames} games: their stats are blended with past
          rookies from the same draft range
          {fantasy.rookieShrinkGames !== null && <> (weighted like {fantasy.rookieShrinkGames} extra games)</>}, and their
          games come from the same updated-forecast model. Not ranked: players not on a roster who haven't played this
          season.
        </p>
      </div>
    </article>
  )
}

function Segmented({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: { value: string; label: string }[]
  value: string
  onChange: (v: string) => void
}) {
  return (
    <div role="radiogroup" aria-label={label}>
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

function Select({ label, value, onChange, children }: { label: string; value: string; onChange: (v: string) => void; children: React.ReactNode }) {
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
