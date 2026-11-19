import { useState } from 'react'
import type { GameBetaModel } from '../types'

const SIZE = 220
const PAD = 32

/** Predicted chance vs. share of games actually played on the test seasons; on the diagonal is perfect. */
export default function CalibrationChart({ bins }: { bins: GameBetaModel['calibration'] }) {
  const [hover, setHover] = useState<number | null>(null)
  const x = (v: number) => PAD + v * (SIZE - PAD - 8)
  const y = (v: number) => SIZE - PAD - v * (SIZE - PAD - 8)
  const path = bins.map((b, i) => `${i ? 'L' : 'M'}${x(b.predicted)},${y(b.actual)}`).join(' ')
  const shown = hover !== null ? bins[hover] : null
  return (
    <figure className="max-w-xs">
      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="w-full" role="img" aria-label="Calibration chart: predicted chance of playing against the share of games played">
        {[0, 0.5, 1].map((t) => (
          <g key={t} className="text-faint">
            <line x1={x(0)} x2={x(1)} y1={y(t)} y2={y(t)} stroke="var(--color-line)" />
            <text x={PAD - 6} y={y(t) + 3} textAnchor="end" fontSize="9" fill="currentColor">
              {t * 100}%
            </text>
            <text x={x(t)} y={SIZE - PAD + 14} textAnchor="middle" fontSize="9" fill="currentColor">
              {t * 100}%
            </text>
          </g>
        ))}
        <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} stroke="var(--color-faint)" strokeDasharray="4 3" />
        <path d={path} fill="none" stroke="var(--color-accent)" strokeWidth="2" />
        {bins.map((b, i) => (
          <g key={i} onPointerEnter={() => setHover(i)} onPointerLeave={() => setHover(null)}>
            <circle cx={x(b.predicted)} cy={y(b.actual)} r="10" fill="transparent" />
            <circle cx={x(b.predicted)} cy={y(b.actual)} r={hover === i ? 5 : 4} fill="var(--color-accent)" stroke="var(--color-surface)" strokeWidth="2" />
          </g>
        ))}
      </svg>
      <figcaption className="mt-1 text-xs text-faint">
        {shown
          ? `Predicted ${Math.round(shown.predicted * 100)}%, played ${Math.round(shown.actual * 100)}% (${shown.n.toLocaleString('en-US')} games)`
          : 'Across: predicted chance. Up: share actually played. Dashed: perfect.'}
      </figcaption>
    </figure>
  )
}
