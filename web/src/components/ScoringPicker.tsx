import { FORMATS } from '../data'
import { GLOSSARY } from '../glossary'
import type { FantasyFormat } from '../types'
import Tip from './Tip'

/** Fantasy scoring switch: ESPN points, Yahoo points or 9-cat. */
export default function ScoringPicker({ format, onChange }: { format: FantasyFormat; onChange: (f: FantasyFormat) => void }) {
  return (
    <div role="radiogroup" aria-label="Scoring">
      <div className="mb-1 text-xs text-faint">
        Scoring (<Tip tip={GLOSSARY.cat9}>what's 9-cat?</Tip>)
      </div>
      <div className="inline-flex rounded-lg border border-line bg-surface p-0.5">
        {FORMATS.map((f) => (
          <button
            key={f.id}
            role="radio"
            aria-checked={format === f.id}
            onClick={() => onChange(f.id)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${format === f.id ? 'bg-accent text-bg' : 'text-muted hover:text-ink'}`}
          >
            {f.label}
          </button>
        ))}
      </div>
    </div>
  )
}
