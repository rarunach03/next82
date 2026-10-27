import { injuryName, injurySource, isInjured, returnText, shortDate } from '../data'
import type { OutInfo, Override } from '../types'
import Tip from './Tip'

/** The one "Injured" badge used everywhere; what's known and where it's from show on hover or tap. */
export default function InjuredBadge({ p }: { p: { override: Override | null; out: OutInfo | null } }) {
  if (!isInjured(p)) return null
  const injury = injuryName(p)
  const o = p.override
  return (
    <Tip
      className="inline-flex cursor-help rounded-full border border-risky/50 px-2 py-0.5 align-middle text-xs font-semibold text-risky"
      tip={
        <>
          <span className="block font-semibold">
            {injury ? `Out: ${injury}` : 'Out'}
            {o ? `, ${returnText(o)}` : ', no return date yet'}
          </span>
          <span className="mt-1 block text-muted">Source: {injurySource(p)}</span>
          {o?.needsReview && (
            <span className="mt-1 block text-moderate">
              Due for a check since {o.reviewBy ? shortDate(o.reviewBy) : 'recently'}; may be out of date.
            </span>
          )}
        </>
      }
    >
      Injured
    </Tip>
  )
}
