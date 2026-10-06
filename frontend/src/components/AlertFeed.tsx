import { useState } from 'react'
import { actionHeadline, isOverLimit, isRecovering, LEVEL_RANK, orderedReasons, sortByRisk } from '../derive'
import { LEVEL_LABEL, clockFromIso } from '../format'
import type { Alert, WorkerSnapshot } from '../types'

const HEADLINE_KINDS = new Set<Alert['kind']>(['escalated', 'renotify', 'signal_lost'])

export type AckMap = Record<string, string>   // worker_id -> ts of the alert that was acknowledged

interface Entry {
  w: WorkerSnapshot
  latest: Alert
  earlier: Alert[]
}

/** Latest actionable alert per worker, plus that worker's older alerts. */
function buildEntries(alerts: Alert[], workers: WorkerSnapshot[]): Entry[] {
  const byWorker = new Map<string, Alert[]>()
  for (const a of alerts) byWorker.set(a.worker_id, [...(byWorker.get(a.worker_id) ?? []), a])
  const out: Entry[] = []
  for (const w of workers) {
    const list = byWorker.get(w.worker_id) ?? []
    const actionable = list.filter((a) => HEADLINE_KINDS.has(a.kind))
    const latest = actionable[actionable.length - 1]
    if (!latest) continue
    out.push({ w, latest, earlier: list.filter((a) => a !== latest).reverse() })
  }
  return out
}

function ttcText(w: WorkerSnapshot): string | null {
  if (w.signal_lost) return null
  if (isOverLimit(w)) return 'over limit'
  if (w.ttc_min === null) return null
  return w.ttc_min <= 0 ? 'at limit now' : `critical in ~${Math.round(w.ttc_min)} min`
}

function EntryCard({ e, acked, onRest, onAck, onSelect }: {
  e: Entry
  acked: boolean
  onRest: () => void
  onAck: () => void
  onSelect: () => void
}) {
  const [details, setDetails] = useState(false)
  const [history, setHistory] = useState(false)
  const { w, latest } = e
  const lost = latest.kind === 'signal_lost' && w.signal_lost
  const level = lost ? 'LOST' : w.level
  const recovering = isRecovering(w)
  const ttc = ttcText(w)
  return (
    <li className={`entry level-${level} ${acked ? 'acked' : ''}`}>
      <div className="entry-head" onClick={onSelect} role="button" tabIndex={0}
        onKeyDown={(ev) => ev.key === 'Enter' && onSelect()}>
        <span className="time">{clockFromIso(latest.ts)}</span>
        <span className="who-name">{w.profile.name}</span>
        <span className={`level-chip level-${level}`}>{lost ? 'NO SIGNAL' : LEVEL_LABEL[w.level]}</span>
        {ttc && <span className="entry-ttc">{ttc}</span>}
      </div>
      <div className="entry-action">{actionHeadline(latest.action) || 'Check on the worker.'}</div>
      <div className="entry-buttons">
        {recovering
          ? <span className="resting-note">Resting now</span>
          : <button className="btn primary" onClick={onRest}>Send to rest</button>}
        {!acked && <button className="btn" onClick={onAck}>Acknowledge</button>}
        <button className="btn link" onClick={() => setDetails(!details)} aria-expanded={details}>
          Details {details ? '▾' : '▸'}
        </button>
      </div>
      {details && (
        <div className="entry-details">
          <p>{latest.action}</p>
          {latest.reasons.length > 0 && (
            <p><b>Why:</b>{' '}
              {orderedReasons(latest.reasons).map((r, i) => (
                <span key={i} className={r.site ? 'muted' : ''}>{i > 0 && ' · '}{r.text}</span>
              ))}
            </p>
          )}
        </div>
      )}
      {e.earlier.length > 0 && (
        <button className="btn link small" onClick={() => setHistory(!history)} aria-expanded={history}>
          {e.earlier.length} earlier alert{e.earlier.length > 1 ? 's' : ''} {history ? '▾' : '▸'}
        </button>
      )}
      {history && (
        <ul className="earlier">
          {e.earlier.slice(0, 12).map((a, i) => (
            <li key={i}>{clockFromIso(a.ts)} · {a.kind.replace('_', ' ')} · {LEVEL_LABEL[a.level]}</li>
          ))}
        </ul>
      )}
    </li>
  )
}

export function AlertFeed({ alerts, workers, acks, onAck, onRest, onSelect }: {
  alerts: Alert[]
  workers: WorkerSnapshot[]
  acks: AckMap
  onAck: (workerId: string, ts: string) => void
  onRest: (workerId: string) => void
  onSelect: (workerId: string) => void
}) {
  const [showAdvisories, setShowAdvisories] = useState(false)
  const [menu, setMenu] = useState(false)
  const [showResolved, setShowResolved] = useState(false)
  const [showAcked, setShowAcked] = useState(true)

  const minRank = showAdvisories ? LEVEL_RANK.ADVISORY : LEVEL_RANK.WARNING
  const entries = buildEntries(alerts, workers)
  const isActive = (e: Entry) => e.w.signal_lost || LEVEL_RANK[e.w.level] >= minRank
  const sorted = sortByRisk(entries.map((e) => e.w)).map((w) => entries.find((e) => e.w === w)!)
  const active = sorted.filter((e) => isActive(e) && acks[e.w.worker_id] !== e.latest.ts)
  const acked = sorted.filter((e) => isActive(e) && acks[e.w.worker_id] === e.latest.ts)
  const resolved = sorted.filter((e) => !isActive(e) && LEVEL_RANK[e.latest.level] >= minRank)

  const watch = [...workers]
    .filter((w) => !w.signal_lost && !w.resting && w.ttc_min !== null && w.ttc_min > 0)
    .sort((a, b) => a.ttc_min! - b.ttc_min!)
    .slice(0, 3)

  const entryCard = (e: Entry, isAcked: boolean) => (
    <EntryCard key={e.w.worker_id} e={e} acked={isAcked}
      onRest={() => onRest(e.w.worker_id)} onAck={() => onAck(e.w.worker_id, e.latest.ts)}
      onSelect={() => onSelect(e.w.worker_id)} />
  )

  return (
    <section className="feed panel" aria-label="Action needed">
      <div className="feed-head">
        <div className="section-head">
          <span className="eyebrow">Action needed</span>
          <h2>{active.length ? `${active.length} worker${active.length > 1 ? 's' : ''} to act on` : 'Nothing to act on'}</h2>
        </div>
        <div className="menu-wrap">
          <button className="btn icon" onClick={() => setMenu(!menu)} aria-label="Feed options" aria-expanded={menu}>⋯</button>
          {menu && (
            <div className="menu" role="menu">
              <label><input type="checkbox" checked={showAdvisories} onChange={(ev) => setShowAdvisories(ev.target.checked)} /> Include advisories</label>
            </div>
          )}
        </div>
      </div>

      {active.length > 0 ? (
        <ul className="entries">{active.map((e) => entryCard(e, false))}</ul>
      ) : (
        <div className="watch">
          <div className="muted">No action needed right now.</div>
          {watch.length > 0 && (
            <>
              <h3>Who to watch</h3>
              <ul>
                {watch.map((w) => (
                  <li key={w.worker_id} onClick={() => onSelect(w.worker_id)}>
                    <span className="who-name">{w.profile.name}</span>
                    <span className="watch-ttc">{Math.round(w.ttc_min!)}<span className="unit">min</span></span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {acked.length > 0 && (
        <div className="feed-section">
          <button className="btn link small" onClick={() => setShowAcked(!showAcked)}>
            Acknowledged ({acked.length}) {showAcked ? '▾' : '▸'}
          </button>
          {showAcked && <ul className="entries">{acked.map((e) => entryCard(e, true))}</ul>}
        </div>
      )}

      {resolved.length > 0 && (
        <div className="feed-section">
          <button className="btn link small" onClick={() => setShowResolved(!showResolved)}>
            Resolved ({resolved.length}) {showResolved ? '▾' : '▸'}
          </button>
          {showResolved && (
            <ul className="resolved">
              {resolved.map((e) => (
                <li key={e.w.worker_id} onClick={() => onSelect(e.w.worker_id)}>
                  {e.w.profile.name} · last {LEVEL_LABEL[e.latest.level]} at {clockFromIso(e.latest.ts)}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}
