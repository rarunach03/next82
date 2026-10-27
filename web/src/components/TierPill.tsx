import type { Tier } from '../types'

const STYLES: Record<Tier, string> = {
  Safe: 'border-safe/40 text-safe',
  Moderate: 'border-moderate/40 text-moderate',
  Risky: 'border-risky/40 text-risky',
}

/** Availability tier, always written out so color is never the only cue. */
export default function TierPill({ tier, safeLow, riskyLow }: { tier: Tier; safeLow?: number; riskyLow?: number }) {
  const help =
    safeLow && riskyLow
      ? `Based on the low end of the likely range: Safe if it's ${safeLow}+ games, Risky if it's under ${riskyLow}.`
      : undefined
  return (
    <span title={help} className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-semibold ${STYLES[tier]}`}>
      {tier}
    </span>
  )
}
