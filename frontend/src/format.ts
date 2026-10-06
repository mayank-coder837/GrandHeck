import type { Level } from './types'

export const LEVEL_LABEL: Record<Level, string> = {
  NONE: 'OK',
  ADVISORY: 'ADVISORY',
  WARNING: 'WARNING',
  CRITICAL: 'CRITICAL',
}

/** "07:42" in site-local time, from an ISO timestamp that already carries the site offset. */
export function clockFromIso(ts: string): string {
  return ts.slice(11, 16)
}

/** Site-local clock for a minute offset relative to a known (ts, minute) pair. */
export function clockAt(refTs: string, refMinute: number, minute: number, utcOffsetH: number): string {
  const ms = Date.parse(refTs) + (minute - refMinute) * 60_000 + utcOffsetH * 3_600_000
  return new Date(ms).toISOString().slice(11, 16)
}

export function fmt(v: number | null | undefined, digits = 1, unit = ''): string {
  return v === null || v === undefined ? '—' : `${v.toFixed(digits)}${unit}`
}
