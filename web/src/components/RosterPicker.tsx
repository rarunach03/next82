import { useId, useMemo, useState } from 'react'
import { MAX_ROSTER, searchPool, teamPosition, type RosterPlayer } from '../roster/model.ts'

interface Props {
  pool: RosterPlayer[]
  /** Players not offered (already picked). */
  taken: Set<number>
  full: boolean
  onAdd: (p: RosterPlayer) => void
  label?: string
}

/** Search to add a player. Arrow keys move, Enter adds, Escape closes. */
export default function RosterPicker({ pool, taken, full, onAdd, label = 'Add a player' }: Props) {
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
        aria-label={label}
        disabled={full}
        value={query}
        placeholder={full ? `Roster full (${MAX_ROSTER} players)` : `${label} by name`}
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
