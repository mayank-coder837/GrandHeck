import { isOverLimit, isRecovering } from '../derive'
import type { Level, SiteSnapshot, WorkerSnapshot } from '../types'

const WARNING_HORIZON_MIN = 20     // the Warning tier; sooner than this the stat is alarming
const ORDER: Level[] = ['CRITICAL', 'WARNING', 'ADVISORY']

function atRisk(workers: WorkerSnapshot[]): { text: string; alarm: boolean } {
  const counts: Partial<Record<Level, number>> = {}
  let lost = 0
  for (const w of workers) {
    if (w.signal_lost) lost += 1
    else if (w.level !== 'NONE') counts[w.level] = (counts[w.level] ?? 0) + 1
  }
  const parts = ORDER.filter((l) => counts[l]).map((l) => `${counts[l]} ${l.toLowerCase()}`)
  if (lost) parts.push(`${lost} no signal`)
  return {
    text: parts.length ? parts.join(' · ') : workers.length ? `All ${workers.length} safe` : 'Connecting…',
    alarm: !!counts.CRITICAL || !!counts.WARNING || lost > 0,
  }
}

function soonest(workers: WorkerSnapshot[]): { text: string; alarm: boolean } {
  const active = workers.filter((w) => !w.signal_lost && !isRecovering(w))
  const over = active.find((w) => isOverLimit(w) || (w.ttc_min !== null && w.ttc_min <= 0))
  if (over) return { text: `${over.profile.name.split(' ')[0]} · now`, alarm: true }
  const next = active.filter((w) => w.ttc_min !== null).sort((a, b) => a.ttc_min! - b.ttc_min!)[0]
  if (!next) return { text: 'None in the next 2 h', alarm: false }
  const m = Math.round(next.ttc_min!)
  return { text: `${next.profile.name.split(' ')[0]} · ${m} min`, alarm: m <= WARNING_HORIZON_MIN }
}

function siteHeat(site?: SiteSnapshot): { text: string; alarm: boolean } {
  if (!site || site.wbgt_c == null) return { text: '—', alarm: false }
  const heavy = site.limits.heavy?.acclimatized
  const over = heavy == null ? null : site.wbgt_c - heavy
  const tail = over == null ? '' : over > 0 ? ` · +${over.toFixed(1)} over heavy limit` : ' · within heavy limit'
  return { text: `WBGT ${site.wbgt_c.toFixed(1)} °C${tail}`, alarm: site.categories.moderate === 'high' }
}

/** The deck's results slide as a live status bar. Turns into the red statement slide when anyone is critical. */
export function StatStrip({ workers, site }: { workers: WorkerSnapshot[]; site?: SiteSnapshot }) {
  const statement = workers.some((w) => w.level === 'CRITICAL' && !w.signal_lost)
  const stats = [
    { ...atRisk(workers), caption: 'Workers at risk' },
    { ...soonest(workers), caption: 'Soonest critical, if nothing changes' },
    { ...siteHeat(site), caption: 'Site heat' },
  ]
  return (
    <section className={`strip ${statement ? 'statement' : ''}`} aria-live="polite" aria-label="Crew status">
      {stats.map((s) => (
        <div key={s.caption} className={`stat ${s.alarm ? 'alarm' : ''}`}>
          <div className="stat-value">{s.text}</div>
          <div className="stat-caption">{s.caption}</div>
        </div>
      ))}
    </section>
  )
}
