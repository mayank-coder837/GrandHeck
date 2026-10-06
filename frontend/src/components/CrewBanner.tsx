import { LEVEL_RANK } from '../derive'
import type { Level, SiteSnapshot, WorkerSnapshot } from '../types'

const ORDER: Level[] = ['CRITICAL', 'WARNING', 'ADVISORY']

/** Site-wide heat stated once, relative to the strictest common limit (heavy work, acclimatized). */
function siteHeatLine(site?: SiteSnapshot): string | null {
  if (!site || site.wbgt_c == null) return null
  const heavy = site.limits.heavy?.acclimatized
  if (heavy == null) return `Site heat: WBGT ${site.wbgt_c.toFixed(1)} °C`
  const diff = site.wbgt_c - heavy
  return diff > 0
    ? `Site heat: WBGT ${site.wbgt_c.toFixed(1)} °C — ${diff.toFixed(1)} °C over the heavy-work limit`
    : `Site heat: WBGT ${site.wbgt_c.toFixed(1)} °C — within the heavy-work limit`
}

export function CrewBanner({ workers, site }: { workers: WorkerSnapshot[]; site?: SiteSnapshot }) {
  const counts: Partial<Record<Level, number>> = {}
  let lost = 0
  for (const w of workers) {
    if (w.signal_lost) lost += 1
    else if (w.level !== 'NONE') counts[w.level] = (counts[w.level] ?? 0) + 1
  }
  const worst = workers.reduce<Level>((m, w) => (!w.signal_lost && LEVEL_RANK[w.level] > LEVEL_RANK[m] ? w.level : m), 'NONE')
  const parts = ORDER.filter((l) => counts[l]).map((l) => `${counts[l]} ${l.toLowerCase()}`)
  if (lost) parts.push(`${lost} no signal`)
  const headline = parts.length ? parts.join(' · ') : `All ${workers.length} workers safe`

  return (
    <section className={`banner worst-${parts.length ? worst : 'NONE'}`} aria-live="polite">
      <span className="banner-headline">{workers.length ? headline : 'Connecting…'}</span>
      {siteHeatLine(site) && <span className="banner-site">{siteHeatLine(site)}</span>}
      <span className="banner-caption">Countdowns show time to critical strain if nothing changes.</span>
    </section>
  )
}
