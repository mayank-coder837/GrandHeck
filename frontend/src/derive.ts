// Pure helpers that turn snapshots + tick history into what the UI shows.
// No science here: only presentation choices on top of the backend's numbers.

import type { Level, Tick, WorkerSnapshot } from './types'

export const BASELINE_CORE_C = 37.0          // redline meter: this core temp reads as 0 %
export const FORECAST_MIN_POINTS = 12        // mirrors backend config, for the calibration bar

export const LEVEL_RANK: Record<Level, number> = { NONE: 0, ADVISORY: 1, WARNING: 2, CRITICAL: 3 }

/** Fraction of the way from baseline to the worker's personal limit (may exceed 1). */
export function redlineFraction(w: WorkerSnapshot): number {
  return (w.core_c - BASELINE_CORE_C) / (w.core_limit_c - BASELINE_CORE_C)
}

export function isOverLimit(w: WorkerSnapshot): boolean {
  return !w.signal_lost && w.core_c >= w.core_limit_c
}

/** Resting after an alert: the worker is being looked after, not unattended. */
export function isRecovering(w: WorkerSnapshot): boolean {
  return w.resting && !w.signal_lost && w.level !== 'NONE'
}

/** Minute at which the current, unbroken over-limit stretch began (from tick history). */
export function overLimitSince(ticks: Tick[], w: WorkerSnapshot): number | null {
  if (!isOverLimit(w)) return null
  let since: number | null = null
  for (let i = ticks.length - 1; i >= 0; i--) {
    const p = ticks[i].workers.find((x) => x.worker_id === w.worker_id)?.point
    if (!p || p.core_c === null) continue          // gaps (dropout) don't break the stretch
    if (p.core_c < w.core_limit_c) break
    since = ticks[i].minute
  }
  return since
}

/** Site-local HH:MM of the last tick in which this worker's wearable reported. */
export function lastSeenClock(ticks: Tick[], workerId: string): string | null {
  for (let i = ticks.length - 1; i >= 0; i--) {
    const p = ticks[i].workers.find((x) => x.worker_id === workerId)?.point
    if (p && p.hr !== null) return ticks[i].ts.slice(11, 16)
  }
  return null
}

/** Progress (0-1) toward having enough real data to forecast. */
export function calibrationProgress(ticks: Tick[], workerId: string): number {
  const recent = ticks.slice(-20)
  const n = recent.filter((t) => t.workers.find((x) => x.worker_id === workerId)?.point.core_c != null).length
  return Math.min(1, n / FORECAST_MIN_POINTS)
}

export function formatDuration(minutes: number): string {
  const m = Math.max(0, Math.round(minutes))
  if (m < 60) return `${m} min`
  return `${Math.floor(m / 60)} h ${m % 60} min`
}

// --- reasons ---------------------------------------------------------------
// The backend ranks reasons by magnitude. Site-wide heat reasons are identical
// for everyone, so the dashboard shows them once (crew banner) and keeps the
// worker-specific ones on cards.

export function isSiteReason(r: string): boolean {
  return r.startsWith('WBGT')
}

export function personalReasons(w: WorkerSnapshot): string[] {
  return w.reasons.filter((r) => !isSiteReason(r))
}

/** Personal reasons first, site-wide last. */
export function orderedReasons(reasons: string[]): { text: string; site: boolean }[] {
  return [
    ...reasons.filter((r) => !isSiteReason(r)).map((text) => ({ text, site: false })),
    ...reasons.filter(isSiteReason).map((text) => ({ text, site: true })),
  ]
}

/** Risk-factor tags only; normal attributes are not shown. */
export function riskTags(w: WorkerSnapshot, max = 2): string[] {
  const tags: string[] = []
  if (!w.profile.acclimatized) tags.push('Not acclimatized')
  if (w.workload_observed === 'heavy') {
    tags.push(w.profile.workload === 'heavy' ? 'Heavy work' : 'Now heavy work')
  } else if (w.workload_observed !== w.profile.workload && w.profile.workload === 'light') {
    tags.push(`Now ${w.workload_observed} work`)
  }
  if (w.profile.age_band === '45+') tags.push('Age 45+')
  return tags.slice(0, max)
}

/** "Stop work immediately." from the full protocol text. */
export function actionHeadline(action: string): string {
  const m = action.match(/^.*?[.!](\s|$)/)
  return (m ? m[0] : action).trim()
}

// --- sorting ----------------------------------------------------------------

/** CRITICAL -> signal lost -> WARNING -> ADVISORY -> OK, ties by lowest time-to-critical. */
export function riskRank(w: WorkerSnapshot): number {
  if (w.signal_lost) return 2.5
  return LEVEL_RANK[w.level]
}

export function sortByRisk(workers: WorkerSnapshot[]): WorkerSnapshot[] {
  return [...workers].sort((a, b) => {
    const r = riskRank(b) - riskRank(a)
    if (r !== 0) return r
    const ta = a.ttc_min ?? Infinity
    const tb = b.ttc_min ?? Infinity
    if (ta !== tb) return ta - tb
    return a.worker_id.localeCompare(b.worker_id)
  })
}
