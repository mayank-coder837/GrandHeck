import { isRecovering } from '../derive'
import type { Tick, WorkerSnapshot } from '../types'

const PAST_MIN = 60
const AHEAD_MIN = 60
const MIN_SPAN_C = 0.6        // keep flat lines from looking jumpy
const W = 240
const H = 36

const TONE: Record<string, string> = {
  NONE: '#94a3b8',
  ADVISORY: '#facc15',
  WARNING: '#fb923c',
  CRITICAL: '#f87171',
  recovering: '#2dd4bf',
  lost: '#64748b',
}

/**
 * The card's signature visual: last hour of estimated core temperature, the
 * forecast as a dashed segment, and this worker's danger limit as a red line.
 */
export function Sparkline({ w, ticks }: { w: WorkerSnapshot; ticks: Tick[] }) {
  const last = ticks[ticks.length - 1]
  if (!last) return <div className="spark" />
  const now = last.minute
  const from = now - PAST_MIN
  const to = now + AHEAD_MIN

  const past: [number, number | null][] = ticks
    .filter((t) => t.minute >= from)
    .map((t) => [t.minute, t.workers.find((x) => x.worker_id === w.worker_id)?.point.core_c ?? null])
  const showForecast = !w.forecast_stale && !w.signal_lost && w.forecast_line.length > 0
  const future: [number, number][] = showForecast
    ? [[now, w.core_c], ...w.forecast_line.filter(([k]) => k > 0 && k <= AHEAD_MIN).map(([k, v]) => [now + k, v] as [number, number])]
    : []

  const values = [w.core_limit_c, ...past.map(([, v]) => v).filter((v): v is number => v != null), ...future.map(([, v]) => v)]
  let lo = Math.min(...values) - 0.1
  let hi = Math.max(...values) + 0.1
  if (hi - lo < MIN_SPAN_C) {
    const mid = (hi + lo) / 2
    lo = mid - MIN_SPAN_C / 2
    hi = mid + MIN_SPAN_C / 2
  }
  const x = (m: number) => ((m - from) / (to - from)) * W
  const y = (v: number) => H - ((v - lo) / (hi - lo)) * H

  // Gaps (sensor dropout) split the history into separate segments.
  const segments: string[] = []
  let cur: string[] = []
  for (const [m, v] of past) {
    if (v == null) { if (cur.length) segments.push(cur.join(' ')); cur = []; continue }
    cur.push(`${x(m).toFixed(1)},${y(v).toFixed(1)}`)
  }
  if (cur.length) segments.push(cur.join(' '))

  const tone = w.signal_lost ? 'lost' : isRecovering(w) ? 'recovering' : w.level
  const color = TONE[tone]
  const limitY = y(w.core_limit_c)

  return (
    <svg className="spark" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img"
      aria-label={`Core temperature ${w.core_c.toFixed(1)} °C, limit ${w.core_limit_c.toFixed(1)} °C`}>
      <title>{`Core ${w.core_c.toFixed(1)} °C · limit ${w.core_limit_c.toFixed(1)} °C · last hour and forecast`}</title>
      <rect x={0} y={0} width={W} height={Math.max(0, limitY)} fill="#ef4444" opacity={0.08} />
      <line x1={0} x2={W} y1={limitY} y2={limitY} stroke="#ef4444" strokeWidth={1.25} vectorEffect="non-scaling-stroke" />
      <line x1={x(now)} x2={x(now)} y1={0} y2={H} stroke="#334155" strokeWidth={1} vectorEffect="non-scaling-stroke" />
      {segments.map((pts, i) => (
        <polyline key={i} points={pts} fill="none" stroke={color} strokeWidth={2} vectorEffect="non-scaling-stroke"
          strokeLinejoin="round" strokeLinecap="round" />
      ))}
      {future.length > 1 && (
        <polyline points={future.map(([m, v]) => `${x(m).toFixed(1)},${y(v).toFixed(1)}`).join(' ')} fill="none"
          stroke={color} strokeWidth={2} strokeDasharray="4 3" opacity={0.8} vectorEffect="non-scaling-stroke" />
      )}
    </svg>
  )
}
