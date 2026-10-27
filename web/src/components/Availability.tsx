import { GLOSSARY, NO_TIER_LABEL } from '../glossary'
import type { NoTierReason, Tier } from '../types'
import TierPill from './TierPill'
import Tip from './Tip'

/** The availability tier, or a short reason there isn't one (explained on hover or tap). */
export default function Availability({
  tier,
  reason,
  safeLow,
  riskyLow,
}: {
  tier: Tier | null
  reason: NoTierReason | null
  safeLow: number
  riskyLow: number
}) {
  if (tier) return <TierPill tier={tier} safeLow={safeLow} riskyLow={riskyLow} />
  if (!reason) return <span className="text-faint">–</span>
  return (
    <Tip
      tip={GLOSSARY.noTier[reason]}
      className="cursor-help text-xs text-muted underline decoration-faint decoration-dotted underline-offset-4"
    >
      {NO_TIER_LABEL[reason]}
    </Tip>
  )
}
