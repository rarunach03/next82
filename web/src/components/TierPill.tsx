import type { Tier } from '../types'
import Tip from './Tip'
import { GLOSSARY } from '../glossary'

const STYLES: Record<Tier, string> = {
  Safe: 'border-safe/40 text-safe',
  Moderate: 'border-moderate/40 text-moderate',
  Risky: 'border-risky/40 text-risky',
}

/**
 * Availability tier, always written out so color is never the only cue. With the
 * cutoffs, it explains itself on hover or tap; `label` adds "Availability:" in front.
 */
export default function TierPill({
  tier,
  safeLow,
  riskyLow,
  label = false,
}: {
  tier: Tier
  safeLow?: number
  riskyLow?: number
  label?: boolean
}) {
  const pill = (
    <span className={`inline-flex rounded-full border px-2 py-0.5 align-middle text-xs font-semibold ${STYLES[tier]}`}>
      {label ? `Availability: ${tier}` : tier}
    </span>
  )
  if (!safeLow || !riskyLow) return pill
  return (
    <Tip tip={GLOSSARY.tier(safeLow, riskyLow)} className="cursor-help">
      {pill}
    </Tip>
  )
}
