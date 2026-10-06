import { useLayoutEffect, useRef, type ReactNode } from 'react'
import { riskRank, sortByRisk } from '../derive'
import type { WorkerSnapshot } from '../types'

/**
 * Risk-sorted order that only re-sorts when someone's level (or signal) changes,
 * so cards don't shuffle every tick while the presenter is clicking.
 */
export function useStableRiskOrder(workers: WorkerSnapshot[]): string[] {
  const order = useRef<string[]>([])
  const signature = useRef('')
  const sig = workers.map((w) => `${w.worker_id}:${riskRank(w)}`).sort().join('|')
  const sameSet = order.current.length === workers.length && workers.every((w) => order.current.includes(w.worker_id))
  if (sig !== signature.current || !sameSet) {
    order.current = sortByRisk(workers).map((w) => w.worker_id)
    signature.current = sig
  }
  return order.current
}

/** FLIP animation: when cards change position, slide them from where they were. */
function useFlip(keys: string[], container: React.RefObject<HTMLDivElement | null>) {
  const last = useRef<Map<string, DOMRect>>(new Map())
  useLayoutEffect(() => {
    const el = container.current
    if (!el) return
    const next = new Map<string, DOMRect>()
    el.querySelectorAll<HTMLElement>('[data-flip]').forEach((node) => {
      const key = node.dataset.flip!
      const rect = node.getBoundingClientRect()
      next.set(key, rect)
      const prev = last.current.get(key)
      if (prev && (prev.left !== rect.left || prev.top !== rect.top)) {
        node.animate(
          [{ transform: `translate(${prev.left - rect.left}px, ${prev.top - rect.top}px)` }, { transform: 'none' }],
          { duration: 450, easing: 'cubic-bezier(0.2, 0.8, 0.2, 1)' },
        )
      }
    })
    last.current = next
  }, [keys.join(','), container])
}

export function CrewGrid({ order, children }: { order: string[]; children: (id: string) => ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  useFlip(order, ref)
  return (
    <div className="grid" ref={ref}>
      {order.map((id) => (
        <div key={id} data-flip={id} className="grid-cell">{children(id)}</div>
      ))}
    </div>
  )
}
