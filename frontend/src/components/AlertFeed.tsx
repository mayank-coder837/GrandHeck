import { useState } from 'react'
import { LEVEL_LABEL, clockFromIso } from '../format'
import type { Alert, Profile } from '../types'

const KIND_TEXT: Record<Alert['kind'], string> = {
  escalated: '',
  renotify: 'still',
  resolved: 'eased to',
  signal_lost: 'SIGNAL LOST',
  signal_restored: 'signal restored',
}

export function AlertFeed({ alerts, profiles, onSelect }: {
  alerts: Alert[]
  profiles: Profile[]
  onSelect: (workerId: string) => void
}) {
  const [showAll, setShowAll] = useState(false)
  const names = Object.fromEntries(profiles.map((p) => [p.worker_id, p.name]))
  // By default show what a supervisor must act on: escalations to Warning/Critical and signal loss.
  const shown = alerts
    .filter((a) => showAll || (a.kind === 'escalated' && a.level !== 'ADVISORY') || a.kind === 'signal_lost')
    .slice(-40)
    .reverse()

  return (
    <section className="feed">
      <div className="feed-head">
        <h2>Alerts</h2>
        <label className="toggle">
          <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} />
          all events
        </label>
      </div>
      {shown.length === 0 && <div className="empty">No active warnings.</div>}
      <ul>
        {shown.map((a, i) => {
          const isSignal = a.kind === 'signal_lost' || a.kind === 'signal_restored'
          const compact = a.kind === 'renotify' || a.kind === 'resolved' || a.kind === 'signal_restored'
          return (
            <li
              key={`${a.ts}-${a.worker_id}-${a.kind}-${i}`}
              className={`alert level-${isSignal ? 'LOST' : a.level} ${compact ? 'compact' : ''}`}
              onClick={() => onSelect(a.worker_id)}
            >
              <div className="alert-head">
                <span className="time">{clockFromIso(a.ts)}</span>
                <span className="who">{names[a.worker_id] ?? a.worker_id}</span>
                <span className={`level-chip level-${isSignal ? 'LOST' : a.level}`}>
                  {KIND_TEXT[a.kind]} {isSignal ? '' : LEVEL_LABEL[a.level]}
                </span>
                {a.ttc_min !== null && a.ttc_min > 0 && a.kind === 'escalated' && (
                  <span className="ttc-inline">critical in ~{Math.round(a.ttc_min)} min</span>
                )}
              </div>
              {!compact && a.reasons.length > 0 && (
                <div className="why"><b>Why:</b> {a.reasons.join(' · ')}</div>
              )}
              {!compact && a.action && <div className="action"><b>Do:</b> {a.action}</div>}
            </li>
          )
        })}
      </ul>
    </section>
  )
}
