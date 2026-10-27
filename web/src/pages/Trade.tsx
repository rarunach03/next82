import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { fantasyValue, plain, useFantasy } from '../data'
import type { Fantasy, FantasyFormat, FantasyPlayer } from '../types'

const FORMATS: { id: FantasyFormat; label: string; unit: string }[] = [
  { id: 'espn', label: 'ESPN points', unit: 'points' },
  { id: 'yahoo', label: 'Yahoo points', unit: 'points' },
  { id: 'cat9', label: '9-cat', unit: 'z-score' },
]

interface Line {
  p: FantasyPlayer
  value: number
  low: number
  high: number
}

/** Rest-of-season value of a player, with a likely range from their games range. */
function line(p: FantasyPlayer, format: FantasyFormat, replacement: number): Line {
  const perGame = p.perGame[format]
  const value = fantasyValue(perGame, replacement, p.restGames)
  const ends = [p.restLow ?? p.restGames, p.restHigh ?? p.restGames].map((g) => fantasyValue(perGame, replacement, g))
  return { p, value, low: Math.min(...ends), high: Math.max(...ends) }
}

const ids = (raw: string | null) => (raw ? raw.split(',').map(Number).filter(Boolean) : [])

/** Compare the rest-of-season fantasy value of two sides of a trade. Runs in the browser; the URL holds the trade. */
export default function Trade() {
  const fantasy = useFantasy()
  const [params, setParams] = useSearchParams()
  const format = (params.get('format') as FantasyFormat) || 'espn'
  const sides = { a: ids(params.get('a')), b: ids(params.get('b')) }

  function update(key: string, value: string | null) {
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        if (value) next.set(key, value)
        else next.delete(key)
        return next
      },
      { replace: true },
    )
  }
  const setSide = (side: 'a' | 'b', list: number[]) => update(side, list.length ? list.join(',') : null)

  if (fantasy === undefined) return <p className="py-16 text-muted">Loading…</p>
  if (fantasy === null) return <p className="py-16 text-muted">Fantasy values aren't available yet.</p>

  const byId = new Map(fantasy.players.map((p) => [p.id, p]))
  const replacement = fantasy.replacement[format]
  const unit = FORMATS.find((f) => f.id === format)!.unit
  const lines = (side: 'a' | 'b') => sides[side].map((id) => byId.get(id)).filter(Boolean).map((p) => line(p!, format, replacement))
  const a = lines('a')
  const b = lines('b')
  const total = (ls: Line[], k: 'value' | 'low' | 'high') => ls.reduce((s, l) => s + l[k], 0)
  const diff = total(b, 'value') - total(a, 'value')
  const fmt = (v: number) => Math.round(v).toLocaleString('en-US')

  return (
    <article className="pt-10 pb-16">
      <p className="text-sm font-semibold tracking-widest text-accent uppercase">Fantasy</p>
      <h1 className="mt-2 font-display text-5xl leading-none font-extrabold tracking-tight uppercase">Trade analyzer</h1>
      <p className="mt-4 max-w-2xl text-muted">
        Compare the rest-of-season value of two sides: per-game production above replacement times the games each player
        is forecast to play from here on. Pick the players you'd give and the players you'd get; the link updates so you
        can share the trade.
      </p>

      <div className="mt-6" role="radiogroup" aria-label="Scoring">
        <div className="mb-1 text-xs text-faint">Scoring</div>
        <div className="inline-flex rounded-lg border border-line bg-surface p-0.5">
          {FORMATS.map((f) => (
            <button
              key={f.id}
              role="radio"
              aria-checked={format === f.id}
              onClick={() => update('format', f.id === 'espn' ? null : f.id)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
                format === f.id ? 'bg-accent text-bg' : 'text-muted hover:text-ink'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <Side title="You give" lines={a} fantasy={fantasy} taken={[...sides.a, ...sides.b]} onChange={(l) => setSide('a', l)} fmt={fmt} />
        <Side title="You get" lines={b} fantasy={fantasy} taken={[...sides.a, ...sides.b]} onChange={(l) => setSide('b', l)} fmt={fmt} />
      </div>

      {a.length > 0 && b.length > 0 && (
        <section className="mt-6 rounded-2xl border border-line bg-surface px-5 py-5">
          <div className="text-sm text-muted">Verdict (rest of season, {FORMATS.find((f) => f.id === format)!.label})</div>
          <p className="mt-1 font-display text-3xl font-bold">
            {Math.abs(diff) < 1 ? (
              'An even trade'
            ) : (
              <>
                You {diff > 0 ? 'gain' : 'lose'} <span className={diff > 0 ? 'text-up' : 'text-down'}>{fmt(Math.abs(diff))}</span>{' '}
                {unit}
              </>
            )}
          </p>
          <p className="mt-2 text-sm text-faint">
            Likely ranges: you give {fmt(total(a, 'low'))}–{fmt(total(a, 'high'))}, you get {fmt(total(b, 'low'))}–
            {fmt(total(b, 'high'))}. Ranges come from each player's likely games and add up the bad and good cases, so
            they're on the wide side. Roster spots aren't counted: a 2-for-1 also frees a spot for a free agent.
          </p>
        </section>
      )}
      <p className="mt-4 text-xs text-faint">
        Values are measured above replacement level (the {fantasy.poolSize}th-best player per game). See the{' '}
        <Link to={`/rankings${format === 'espn' ? '' : `?format=${format}`}`} className="text-accent">
          rankings
        </Link>{' '}
        for every player.
      </p>
    </article>
  )
}

function Side({
  title,
  lines,
  fantasy,
  taken,
  onChange,
  fmt,
}: {
  title: string
  lines: Line[]
  fantasy: Fantasy
  taken: number[]
  onChange: (ids: number[]) => void
  fmt: (v: number) => string
}) {
  const [query, setQuery] = useState('')
  const matches = useMemo(() => {
    const q = plain(query.trim())
    if (!q) return []
    // Whole-name or word matches first ("jalen w", "williams"), then anywhere in the name.
    const rank = (name: string) => (name.startsWith(q) || name.split(' ').some((w) => w.startsWith(q)) ? 0 : name.includes(q) ? 1 : 2)
    return fantasy.players
      .filter((p) => !taken.includes(p.id) && rank(plain(p.name)) < 2)
      .sort((x, y) => rank(plain(x.name)) - rank(plain(y.name)) || y.restGames * y.perGame.espn - x.restGames * x.perGame.espn)
      .slice(0, 6)
  }, [query, fantasy, taken])
  const current = lines.map((l) => l.p.id)

  return (
    <section className="rounded-2xl border border-line bg-surface p-4">
      <h2 className="font-display text-2xl font-bold uppercase">{title}</h2>
      <div className="relative mt-3">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Add a player"
          aria-label={`${title}: add a player`}
          className="w-full rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm text-ink placeholder:text-faint outline-none focus:border-accent"
        />
        {matches.length > 0 && (
          <ul className="absolute z-10 mt-1 w-full overflow-hidden rounded-lg border border-line bg-surface-2 shadow-xl">
            {matches.map((p) => (
              <li key={p.id}>
                <button
                  onClick={() => {
                    onChange([...current, p.id])
                    setQuery('')
                  }}
                  className="flex w-full justify-between px-3 py-2 text-left text-sm hover:bg-line"
                >
                  <span>
                    {p.name} <span className="text-xs text-faint">{p.team}</span>
                  </span>
                  <span className="text-xs text-muted">{Math.round(p.restGames)} games left</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      <ul className="mt-3 divide-y divide-line">
        {lines.length === 0 && <li className="py-3 text-sm text-faint">No players yet</li>}
        {lines.map((l) => (
          <li key={l.p.id} className="flex items-start justify-between gap-3 py-3">
            <div className="min-w-0">
              <div className="font-medium">
                {l.p.name} <span className="text-xs text-faint">{l.p.team}</span>
                {l.p.override && <span className="ml-1 text-xs font-semibold text-risky">· out</span>}
              </div>
              <div className="text-xs text-muted">
                {Math.round(l.p.restGames)} games left
                {l.p.restLow !== null && l.p.restHigh !== null && (
                  <span className="text-faint">
                    {' '}
                    (likely {Math.round(l.p.restLow)}–{Math.round(l.p.restHigh)})
                  </span>
                )}
              </div>
            </div>
            <div className="text-right">
              <div className="tabular font-semibold">{fmt(l.value)}</div>
              <div className="tabular text-xs text-faint">
                {fmt(l.low)}–{fmt(l.high)}
              </div>
              <button onClick={() => onChange(current.filter((id) => id !== l.p.id))} className="mt-1 text-xs text-muted hover:text-ink">
                Remove
              </button>
            </div>
          </li>
        ))}
      </ul>
      {lines.length > 0 && (
        <div className="mt-2 flex justify-between border-t border-line pt-3 text-sm">
          <span className="text-muted">Total</span>
          <span className="tabular font-semibold">{fmt(lines.reduce((s, l) => s + l.value, 0))}</span>
        </div>
      )}
    </section>
  )
}
