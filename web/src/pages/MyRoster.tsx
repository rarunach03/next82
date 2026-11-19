import { useEffect, useId, useMemo, useState } from 'react'
import { Link } from 'react-router'
import Availability from '../components/Availability'
import InjuredBadge from '../components/InjuredBadge'
import Tip from '../components/Tip'
import { GLOSSARY } from '../glossary'
import { isInjured, useFantasy } from '../data'
import { MAX_ROSTER, rosterPool, searchPool, type RosterPlayer } from '../roster/model.ts'
import { loadSaved, save, type Saved } from '../roster/storage.ts'
import type { Index } from '../types'

/** Build (or enter) a fantasy roster and see how its availability holds up. Saved in this browser. */
export default function MyRoster({ index }: { index: Index }) {
  const fantasy = useFantasy()
  const [saved, setSaved] = useState<Saved>(loadSaved)
  useEffect(() => save(saved), [saved])

  const pool = useMemo(() => (fantasy === undefined ? null : rosterPool(index.players, fantasy)), [index, fantasy])
  if (!pool) return <p className="py-16 text-muted">Loading…</p>

  const byId = new Map(pool.map((p) => [p.id, p]))
  // Saved players who left the pool (released, no forecast) are dropped from view but kept in storage.
  const roster = saved.ids.map((id) => byId.get(id)).filter((p): p is RosterPlayer => p !== undefined)
  const missing = saved.ids.length - roster.length
  const setIds = (ids: number[]) => setSaved((s) => ({ ...s, ids }))
  const add = (p: RosterPlayer) => saved.ids.length < MAX_ROSTER && setIds([...saved.ids, p.id])
  const remove = (id: number) => setIds(saved.ids.filter((i) => i !== id))
  const { meta } = index

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
          <Picker pool={pool} taken={new Set(saved.ids)} full={saved.ids.length >= MAX_ROSTER} onAdd={add} />
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
          <RosterTable roster={roster} onRemove={remove} safeLow={meta.tierSafeLow} riskyLow={meta.setbackGames} />
        )}
      </section>
    </article>
  )
}

/** Search to add a player. Arrow keys move, Enter adds, Escape closes. */
function Picker({
  pool,
  taken,
  full,
  onAdd,
}: {
  pool: RosterPlayer[]
  taken: Set<number>
  full: boolean
  onAdd: (p: RosterPlayer) => void
}) {
  const listId = useId()
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const results = useMemo(() => searchPool(pool, query, taken), [pool, query, taken])
  const showList = open && query.trim() !== ''

  function choose(p: RosterPlayer) {
    onAdd(p)
    setQuery('')
    setActive(0)
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setOpen(true)
      setActive((i) => Math.min(i + 1, results.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter' && results[active]) {
      e.preventDefault()
      choose(results[active])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div className="relative">
      <input
        role="combobox"
        aria-expanded={showList}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={showList && results[active] ? `${listId}-${active}` : undefined}
        aria-label="Add a player"
        disabled={full}
        value={query}
        placeholder={full ? `Roster full (${MAX_ROSTER} players)` : 'Add a player by name'}
        onChange={(e) => {
          setQuery(e.target.value)
          setActive(0)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onKeyDown={onKeyDown}
        className="w-full rounded-xl border border-line bg-surface px-4 py-3 text-ink placeholder:text-faint outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/30 disabled:opacity-60"
      />
      {showList && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-20 mt-2 w-full overflow-hidden rounded-xl border border-line bg-surface-2 shadow-2xl shadow-black/50"
        >
          {results.length === 0 && <li className="px-4 py-3 text-sm text-muted">No players found</li>}
          {results.map((p, i) => (
            <li
              key={p.id}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => choose(p)}
              onMouseEnter={() => setActive(i)}
              className={`flex cursor-pointer items-center justify-between gap-3 px-4 py-2.5 ${i === active ? 'bg-line' : ''}`}
            >
              <span className="min-w-0 truncate">
                <span className="font-medium">{p.name}</span>
                <span className="ml-2 text-sm text-faint">{teamPosition(p)}</span>
              </span>
              <span className="tabular shrink-0 text-sm text-muted">{Math.round(p.rest)} games left</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** "LAL · F-C", "LAL" (no position yet), or the position alone. */
function teamPosition(p: RosterPlayer): string {
  return [p.team, p.position].filter(Boolean).join(' · ')
}

function RosterTable({
  roster,
  onRemove,
  safeLow,
  riskyLow,
}: {
  roster: RosterPlayer[]
  onRemove: (id: number) => void
  safeLow: number
  riskyLow: number
}) {
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
            <th className="w-10 py-3 pr-3 sm:pr-4">
              <span className="sr-only">Remove</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {roster.map((p) => (
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
              </td>
              <td className="tabular hidden py-3 pr-2 whitespace-nowrap text-muted sm:table-cell sm:pr-3">
                {p.restLow !== null && p.restHigh !== null ? `${Math.round(p.restLow)}–${Math.round(p.restHigh)}` : '–'}
              </td>
              <td className="hidden py-3 pr-2 sm:table-cell sm:pr-3">
                <Availability tier={p.tier} reason={p.noTierReason} safeLow={safeLow} riskyLow={riskyLow} />
              </td>
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
      </table>
    </div>
  )
}
