/**
 * A forecast and its likely range (10th-90th percentile) on a 0-82 scale: the
 * shaded band is the range, the tick is the forecast. The numbers are printed
 * beside it, so the bar is never the only way to read the range.
 */
export default function RangeBar({ low, point, high, accent = false }: { low: number; point: number; high: number; accent?: boolean }) {
  const pct = (v: number) => `${Math.max(0, Math.min(100, (v / 82) * 100))}%`
  return (
    <div className="mt-3">
      <div className="relative h-2 rounded-full bg-surface-2" aria-hidden>
        <div
          className={`absolute inset-y-0 rounded-full ${accent ? 'bg-accent/35' : 'bg-ink/25'}`}
          style={{ left: pct(low), width: `calc(${pct(high)} - ${pct(low)})` }}
        />
        <div
          className={`absolute -inset-y-1 w-1 -translate-x-1/2 rounded-full ${accent ? 'bg-accent' : 'bg-ink'}`}
          style={{ left: pct(point) }}
        />
      </div>
      <div className="mt-1.5 text-xs text-muted">
        Likely <span className="tabular text-ink">{Math.round(low)}–{Math.round(high)}</span> games
      </div>
    </div>
  )
}
