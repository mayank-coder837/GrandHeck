// Shared chart styling and time-axis helpers (detail view, shift overview).

import type { Tick } from './types'

export const CHART = {
  core: '#38bdf8',
  truth: '#94a3b8',
  forecast: '#fb923c',
  band: '#fb923c',
  limit: '#ef4444',
  hr: '#f472b6',
  psi: '#a78bfa',
  wbgt: '#facc15',
  grid: 'rgba(148,163,184,0.12)',
  axis: '#8a9bb8',
  warning: '#fb923c',
  critical: '#ef4444',
}
export const TOOLTIP_STYLE = { background: '#0f172a', border: '1px solid #334155', borderRadius: 8, color: '#e5ecf6', fontSize: 12 }
export const AXIS_TICK = { fontSize: 12, fill: CHART.axis }

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
