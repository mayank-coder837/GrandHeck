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

export function fmt(v: number | null | undefined, digits = 1, unit = ''): string {
  return v === null || v === undefined ? '—' : `${v.toFixed(digits)}${unit}`
}
