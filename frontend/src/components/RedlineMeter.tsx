import { redlineFraction } from '../derive'
import type { WorkerSnapshot } from '../types'

/**
 * How close the estimated core temperature is to this worker's personal danger
 * limit: baseline (~37.0 °C) at the left, the limit as a red line at the right.
 */
export function RedlineMeter({ w, recovering }: { w: WorkerSnapshot; recovering: boolean }) {
  const f = redlineFraction(w)
  const pct = Math.max(0, Math.min(1, f)) * 100
  const over = f >= 1
  const tone = w.signal_lost ? 'lost' : recovering ? 'recovering' : w.level
  return (
    <div
      className={`meter tone-${tone} ${over ? 'over' : ''}`}
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(f * 100)}
      aria-label={`Core ${w.core_c.toFixed(1)} °C of ${w.core_limit_c.toFixed(1)} °C limit`}
      title={`Core ${w.core_c.toFixed(1)} °C · limit ${w.core_limit_c.toFixed(1)} °C`}
    >
      <div className="meter-fill" style={{ width: `${pct}%` }} />
      <div className="meter-limit" />
    </div>
  )
}
