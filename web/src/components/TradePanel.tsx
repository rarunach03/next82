import { useState } from 'react'
import { FORMATS } from '../data'
import { GLOSSARY } from '../glossary'
import type { Flag } from '../roster/flags.ts'
import { MAX_ROSTER, restValue, teamPosition, type RosterPlayer } from '../roster/model.ts'
import type { Simulation } from '../roster/simulate.ts'
import { sideValue, togglePlayer, verdict, type SideValue, type Trade } from '../roster/trade.ts'
import type { Fantasy, FantasyFormat } from '../types'
import RosterPicker from './RosterPicker'
import Tip from './Tip'

interface Outlook {
  sim: Simulation
  flags: Flag[]
}

const whole = (v: number) => Math.round(v).toLocaleString('en-US')
const signed = (v: number) => (Math.round(v) === 0 ? '–' : `${v > 0 ? '+' : '−'}${whole(Math.abs(v))}`)

/**
 * Test a trade on My Roster: pick players to give (from the roster) and to get, see
 * each side's rest-of-season value and the verdict, and how the roster's season
 * simulation and risk check change. The trade lives in the URL.
 */
export default function TradePanel({
  trade,
  onChange,
  onApply,
  roster,
  pool,
  fantasy,
  format,
  before,
  after,
}: {
  trade: Trade
  onChange: (t: Trade | null) => void
  onApply: () => void
  roster: RosterPlayer[]
  pool: RosterPlayer[]
  fantasy: Fantasy
  format: FantasyFormat
  before: Outlook
  after: Outlook & { players: RosterPlayer[] }
}) {
  const [copied, setCopied] = useState(false)
  const byId = new Map(pool.map((p) => [p.id, p]))
  const pick = (ids: number[]) => ids.map((id) => byId.get(id)).filter((p): p is RosterPlayer => p !== undefined)
  const give = pick(trade.give)
  const get = pick(trade.get)
  const onRoster = new Set(roster.map((p) => p.id))
  const offRoster = give.filter((p) => !onRoster.has(p.id))
  const replacement = fantasy.replacement[format]
  const unit = format === 'cat9' ? 'z-score' : 'points'
  const scoring = FORMATS.find((f) => f.id === format)!.label
  const giveValue = sideValue(give, format, replacement)
  const getValue = sideValue(get, format, replacement)
  const result = verdict(giveValue, getValue)
  const rosterValue = (players: RosterPlayer[]) => players.reduce((s, p) => s + (restValue(p, format, replacement) ?? 0), 0)
  const changed = give.some((p) => onRoster.has(p.id)) || get.length > 0

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(window.location.href)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Clipboard blocked: the address bar still has the link.
    }
  }

  return (
    <section className="mt-8 rounded-2xl border border-accent/40 bg-surface p-4 sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-2xl font-bold uppercase">Test a trade</h2>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            Pick who you'd give and who you'd get. You'll see what each side is worth from here on and how your roster's
            season outlook and risk check would change. The link updates so you can share the trade.
          </p>
        </div>
        <button
          onClick={() => onChange(null)}
          aria-label="Close the trade"
          className="shrink-0 rounded-md px-2 py-1 text-muted transition hover:bg-surface-2 hover:text-ink"
        >
          ✕
        </button>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <div className="rounded-xl bg-surface-2 p-3">
          <h3 className="font-semibold">You give</h3>
          {roster.length === 0 ? (
            <p className="mt-2 text-sm text-faint">Add players to your roster above to pick who you'd give.</p>
          ) : (
            <div className="mt-2 flex flex-wrap gap-1.5" role="group" aria-label="Players to give">
              {roster.map((p) => {
                const on = trade.give.includes(p.id)
                return (
                  <button
                    key={p.id}
                    aria-pressed={on}
                    onClick={() => onChange(togglePlayer(trade, 'give', p.id))}
                    className={`rounded-full border px-2.5 py-1 text-sm transition ${
                      on ? 'border-accent bg-accent/15 text-ink' : 'border-line text-muted hover:text-ink'
                    }`}
                  >
                    {p.name}
                  </button>
                )
              })}
            </div>
          )}
          <Side players={give} format={format} replacement={replacement} onRemove={(id) => onChange(togglePlayer(trade, 'give', id))} />
          {offRoster.length > 0 && (
            <p className="mt-2 text-xs text-faint">
              From the shared link; not on your roster, so your roster after the trade doesn't change for{' '}
              {offRoster.map((p) => p.name).join(', ')}.
            </p>
          )}
        </div>
        <div className="rounded-xl bg-surface-2 p-3">
          <h3 className="font-semibold">You get</h3>
          <div className="mt-2">
            <RosterPicker
              pool={pool}
              taken={new Set([...onRoster, ...trade.get])}
              full={false}
              onAdd={(p) => onChange(togglePlayer(trade, 'get', p.id))}
              label="Add a player to get"
            />
          </div>
          <Side players={get} format={format} replacement={replacement} onRemove={(id) => onChange(togglePlayer(trade, 'get', id))} />
        </div>
      </div>

      {give.length > 0 && get.length > 0 && (
        <div className="mt-4">
          <div className="text-sm text-muted">Verdict (rest of season, {scoring})</div>
          <p className="mt-1 font-display text-3xl font-bold">
            {result.kind === 'even' ? (
              'An even trade'
            ) : (
              <>
                You {result.kind} <span className={result.kind === 'gain' ? 'text-up' : 'text-down'}>{whole(result.amount)}</span>{' '}
                {unit}
              </>
            )}
          </p>
          <p className="mt-1 text-sm text-faint">
            <Tip tip={GLOSSARY.likelyRange}>Likely ranges</Tip>: you give {whole(giveValue.low)}–{whole(giveValue.high)}, you
            get {whole(getValue.low)}–{whole(getValue.high)}. Ranges add up each player's bad and good cases, so they're on
            the wide side.
            {giveValue.unranked + getValue.unranked > 0 && ' Players without a fantasy ranking count as zero.'}
          </p>
        </div>
      )}

      {changed && (
        <div className="mt-5">
          <h3 className="font-semibold">Your roster after the trade</h3>
          <div className="mt-2 overflow-x-auto rounded-xl border border-line">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs tracking-wide text-faint uppercase">
                  <th className="py-2 pr-2 pl-3 font-medium" />
                  <th className="py-2 pr-2 text-right font-medium">Now</th>
                  <th className="py-2 pr-2 text-right font-medium">After</th>
                  <th className="py-2 pr-3 text-right font-medium">Change</th>
                </tr>
              </thead>
              <tbody className="tabular">
                <Compare label="Players" now={roster.length} next={after.players.length} />
                <Compare label="Expected games left" now={before.sim.mean} next={after.sim.mean} />
                <Compare label="Bad season (1 in 10)" now={before.sim.low} next={after.sim.low} />
                <Compare label="Typical season" now={before.sim.median} next={after.sim.median} />
                <Compare label="Good season (1 in 10)" now={before.sim.high} next={after.sim.high} />
                <Compare label={`Value (${unit})`} now={rosterValue(roster)} next={rosterValue(after.players)} />
              </tbody>
            </table>
          </div>
          {after.players.length > MAX_ROSTER && (
            <p className="mt-2 text-xs text-moderate">
              You'd have {after.players.length} players; drop {after.players.length - MAX_ROSTER} to stay at {MAX_ROSTER}.
            </p>
          )}

          <h4 className="mt-4 text-sm font-semibold">Risk check after the trade</h4>
          <FlagChanges before={before.flags} after={after.flags} />

          <div className="mt-4 flex flex-wrap gap-2">
            <button
              onClick={onApply}
              className="rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-bg transition hover:brightness-110"
            >
              Make this trade on my roster
            </button>
            <button
              onClick={copyLink}
              className="rounded-lg border border-line px-3 py-2 text-sm font-medium text-muted transition hover:text-ink"
            >
              {copied ? 'Link copied' : 'Copy link to this trade'}
            </button>
          </div>
        </div>
      )}
    </section>
  )
}

/** One side's players: games left (likely range) and rest-of-season value. */
function Side({
  players,
  format,
  replacement,
  onRemove,
}: {
  players: RosterPlayer[]
  format: FantasyFormat
  replacement: number
  onRemove: (id: number) => void
}) {
  if (players.length === 0) return null
  const total: SideValue = sideValue(players, format, replacement)
  return (
    <ul className="mt-3 divide-y divide-line">
      {players.map((p) => {
        const value = restValue(p, format, replacement)
        return (
          <li key={p.id} className="flex items-start justify-between gap-3 py-2">
            <div className="min-w-0">
              <div className="truncate text-sm font-medium">
                {p.name} <span className="text-xs text-faint">{teamPosition(p)}</span>
              </div>
              <div className="tabular text-xs text-muted">
                {Math.round(p.rest)} games left
                {p.restLow !== null && p.restHigh !== null && (
                  <span className="text-faint">
                    {' '}
                    (likely {Math.round(p.restLow)}–{Math.round(p.restHigh)})
                  </span>
                )}
              </div>
            </div>
            <div className="flex shrink-0 items-start gap-2">
              <span className="tabular text-sm font-semibold">{value === null ? '–' : whole(value)}</span>
              <button
                onClick={() => onRemove(p.id)}
                aria-label={`Take ${p.name} out of the trade`}
                className="rounded px-1 text-muted hover:text-ink"
              >
                ✕
              </button>
            </div>
          </li>
        )
      })}
      <li className="flex justify-between pt-2 text-sm">
        <span className="text-muted">Total</span>
        <span className="tabular font-semibold">{whole(total.value)}</span>
      </li>
    </ul>
  )
}

function Compare({ label, now, next }: { label: string; now: number; next: number }) {
  const diff = next - now
  return (
    <tr className="border-b border-line/60 last:border-0">
      <td className="py-2 pr-2 pl-3 text-muted">{label}</td>
      <td className="py-2 pr-2 text-right">{whole(now)}</td>
      <td className="py-2 pr-2 text-right font-semibold">{whole(next)}</td>
      <td className={`py-2 pr-3 text-right ${Math.round(diff) > 0 ? 'text-up' : Math.round(diff) < 0 ? 'text-down' : 'text-faint'}`}>
        {signed(diff)}
      </td>
    </tr>
  )
}

/** Warnings after the trade, marking new ones, and the ones the trade clears. */
function FlagChanges({ before, after }: { before: Flag[]; after: Flag[] }) {
  const had = new Set(before.map((f) => f.id))
  const has = new Set(after.map((f) => f.id))
  const cleared = before.filter((f) => !has.has(f.id))
  if (after.length === 0 && cleared.length === 0) return <p className="mt-1 text-sm text-muted">No red flags before or after.</p>
  return (
    <ul className="mt-2 space-y-1.5 text-sm">
      {after.map((f) => (
        <li key={f.id} className="flex gap-2">
          <span aria-hidden className="font-bold text-moderate">!</span>
          <span>
            {!had.has(f.id) && (
              <span className="mr-1.5 rounded-full border border-moderate/50 px-1.5 text-xs font-semibold text-moderate">New</span>
            )}
            {f.text}
          </span>
        </li>
      ))}
      {cleared.map((f) => (
        <li key={f.id} className="flex gap-2 text-muted">
          <span aria-hidden className="font-bold text-safe">✓</span>
          <span>
            <span className="mr-1.5 rounded-full border border-safe/50 px-1.5 text-xs font-semibold text-safe">Cleared</span>
            <span className="line-through decoration-faint">{f.text}</span>
          </span>
        </li>
      ))}
    </ul>
  )
}
