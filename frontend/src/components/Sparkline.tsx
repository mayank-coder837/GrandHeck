import { crossing } from '../chartUtils'
import { useTheme } from '../theme'
import type { Tick, WorkerSnapshot } from '../types'

const PAST_MIN = 60
const AHEAD_MIN = 60
const MIN_SPAN_C = 0.6        // keep flat lines from looking jumpy
const W = 240
const H = 36

/**
 * The card's signature visual, the deck cover's mark made live: the last hour of
 * estimated core temperature, the forecast dashed, this worker's danger limit as
 * a red line, and a red dot where the forecast reaches it.
 */
export function Sparkline({ w, ticks }: { w: WorkerSnapshot; ticks: Tick[] }) {
  const { t } = useTheme()
  const last = ticks[ticks.length - 1]
  if (!last) return <div className="spark" />
  const now = last.minute
  const from = now - PAST_MIN
  const to = now + AHEAD_MIN

  const past: [number, number | null][] = ticks
    .filter((tk) => tk.minute >= from)
    .map((tk) => [tk.minute, tk.workers.find((x) => x.worker_id === w.worker_id)?.point.core_c ?? null])
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

  const limitY = y(w.core_limit_c)
  const cross = future.length > 1 && w.core_c < w.core_limit_c ? crossing(future, w.core_limit_c) : null

  return (
    <svg className="spark" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img"
      aria-label={`Core temperature ${w.core_c.toFixed(1)} °C, limit ${w.core_limit_c.toFixed(1)} °C`}>
      <title>{`Core ${w.core_c.toFixed(1)} °C · limit ${w.core_limit_c.toFixed(1)} °C · last hour and forecast`}</title>
      <line x1={x(now)} x2={x(now)} y1={0} y2={H} stroke={t.border} strokeWidth={1} vectorEffect="non-scaling-stroke" />
      <line x1={1} x2={W - 1} y1={limitY} y2={limitY} stroke={t.red} strokeWidth={1.5} strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      {segments.map((pts, i) => (
        <polyline key={i} points={pts} fill="none" stroke={t['text-2']} strokeWidth={1.5} vectorEffect="non-scaling-stroke"
          strokeLinejoin="round" strokeLinecap="round" />
      ))}
      {future.length > 1 && (
        <polyline points={future.map(([m, v]) => `${x(m).toFixed(1)},${y(v).toFixed(1)}`).join(' ')} fill="none"
          stroke={t.muted} strokeWidth={1.5} strokeDasharray="4 3" vectorEffect="non-scaling-stroke" />
      )}
      {cross && (
        // A circle would stretch with preserveAspectRatio="none"; a zero-length round-capped line stays round.
        <line x1={x(cross[0])} x2={x(cross[0])} y1={limitY} y2={limitY} stroke={t.red} strokeWidth={6} strokeLinecap="round"
          vectorEffect="non-scaling-stroke" />
      )}
    </svg>
  )
}
