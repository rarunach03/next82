import { useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

/**
 * Something with a short explanation that shows on hover, keyboard focus or tap.
 * The popup is drawn on top of the page (not inside tables that scroll), and kept
 * on screen; it closes on scroll, tapping elsewhere or moving away.
 */
export default function Tip({
  tip,
  children,
  className = 'cursor-help underline decoration-faint decoration-dotted underline-offset-4',
}: {
  tip: React.ReactNode
  children: React.ReactNode
  className?: string
}) {
  const ref = useRef<HTMLSpanElement>(null)
  const id = useId()
  const [pos, setPos] = useState<{ x: number; y: number; above: boolean } | null>(null)

  function show() {
    const r = ref.current?.getBoundingClientRect()
    if (!r) return
    const above = r.bottom + 140 > window.innerHeight
    const half = Math.min(130, window.innerWidth / 2 - 8)
    setPos({
      x: Math.min(Math.max(r.left + r.width / 2, half + 8), window.innerWidth - half - 8),
      y: above ? r.top - 6 : r.bottom + 6,
      above,
    })
  }

  useEffect(() => {
    if (!pos) return
    const hide = () => setPos(null)
    const outside = (e: PointerEvent) => !ref.current?.contains(e.target as Node) && hide()
    window.addEventListener('scroll', hide, true)
    window.addEventListener('pointerdown', outside)
    return () => {
      window.removeEventListener('scroll', hide, true)
      window.removeEventListener('pointerdown', outside)
    }
  }, [pos])

  return (
    <span
      ref={ref}
      tabIndex={0}
      aria-describedby={pos ? id : undefined}
      onMouseEnter={show}
      onMouseLeave={() => setPos(null)}
      onFocus={show}
      onBlur={() => setPos(null)}
      // Inside clickable table rows: a tap explains instead of opening the row.
      onClick={(e) => {
        e.stopPropagation()
        e.preventDefault()
        show()
      }}
      className={`outline-none focus-visible:ring-1 focus-visible:ring-accent ${className}`}
    >
      {children}
      {pos &&
        createPortal(
          <span
            id={id}
            role="tooltip"
            style={{ left: pos.x, top: pos.y, transform: `translate(-50%, ${pos.above ? '-100%' : '0'})` }}
            className="pointer-events-none fixed z-50 w-64 max-w-[calc(100vw-16px)] rounded-lg border border-line bg-surface-2 px-3 py-2 text-left text-xs leading-relaxed font-normal tracking-normal text-ink normal-case shadow-xl"
          >
            {tip}
          </span>,
          document.body,
        )}
    </span>
  )
}
