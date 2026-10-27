import { overrideStatus, shortDate } from '../data'
import type { Override } from '../types'

/** Banner for a player whose updated forecast was adjusted by hand from injury news. */
export default function OverrideNote({ override: o }: { override: Override }) {
  return (
    <div className="mt-4 rounded-xl border border-risky/40 bg-risky/10 px-4 py-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-risky/50 px-2 py-0.5 text-xs font-semibold text-risky">Manual adjustment</span>
        <span className="font-semibold text-ink">{overrideStatus(o)}</span>
      </div>
      <p className="mt-1.5 text-ink">{o.note}</p>
      <p className="mt-1 text-xs text-muted">
        <a href={o.sourceUrl} target="_blank" rel="noreferrer" className="text-accent underline-offset-2 hover:underline">
          Source ↗
        </a>
        {o.sourceUrl2 && (
          <>
            {' · '}
            <a href={o.sourceUrl2} target="_blank" rel="noreferrer" className="text-accent underline-offset-2 hover:underline">
              Source 2 ↗
            </a>
          </>
        )}
        {o.dateAdded && <> · added {shortDate(o.dateAdded)}</>}
        {o.reviewBy && <> · to be reviewed by {shortDate(o.reviewBy)}</>}
        {' · '}The updated forecast below uses this; the model can't read injury news on its own.
      </p>
    </div>
  )
}
