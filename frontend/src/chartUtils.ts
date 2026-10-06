// Shared chart styling and time-axis helpers (detail view, shift overview).

import type { Tokens } from './theme'
import type { Tick } from './types'

/** Axis tick style from the active theme tokens (charts can't read CSS variables). */
export function axisTick(t: Tokens) {
  return { fontSize: 12, fill: t.muted, fontFamily: "'IBM Plex Sans', Arial, sans-serif" }
}

/** Where a path first crosses a horizontal limit (linear interpolation), if it does. */
export function crossing(points: [number, number][], limit: number): [number, number] | null {
  for (let i = 1; i < points.length; i++) {
    const [x0, y0] = points[i - 1]
    const [x1, y1] = points[i]
    if (y0 < limit && y1 >= limit) return [x0 + ((limit - y0) / (y1 - y0)) * (x1 - x0), limit]
  }
  return null
}

/** Minute <-> site clock, anchored on the last tick's own HH:MM. */
export function makeClock(last: Tick) {
  const lastMod = Number(last.ts.slice(11, 13)) * 60 + Number(last.ts.slice(14, 16))
  const modOf = (m: number) => (((lastMod + m - last.minute) % 1440) + 1440) % 1440
  const label = (m: number) => {
    const mod = Math.round(modOf(m))
    return `${String(Math.floor(mod / 60)).padStart(2, '0')}:${String(mod % 60).padStart(2, '0')}`
  }
  /** Ticks on round half-hours inside [from, to]. */
  const halfHours = (from: number, to: number) => {
    const out: number[] = []
    const first = from + ((30 - (Math.round(modOf(from)) % 30)) % 30)
    for (let m = first; m <= to; m += 30) out.push(m)
    return out
  }
  return { label, halfHours }
}

export function domainWithPadding(values: number[], pad: number, step = 0.1): [number, number] {
  const lo = Math.min(...values) - pad
  const hi = Math.max(...values) + pad
  return [Math.floor(lo / step) * step, Math.ceil(hi / step) * step]
}

/** Trailing rolling mean, skipping missing values. */
export function rollingMean(values: (number | null)[], window: number): (number | null)[] {
  return values.map((_, i) => {
    const w = values.slice(Math.max(0, i - window + 1), i + 1).filter((v): v is number => v != null)
    return w.length ? w.reduce((a, b) => a + b, 0) / w.length : null
  })
}
