import {
  calibrationProgress, formatDuration, isOverLimit, isRecovering, lastSeenClock, overLimitSince,
  personalReasons, REST_PLACE, restCondition, riskTags,
} from '../derive'
import { LEVEL_LABEL, fmt } from '../format'
import type { Tick, WorkerSnapshot } from '../types'
import { Sparkline } from './Sparkline'

/**
 * How long until it gets critical, as one row: the big value and its state text
 * side by side. Only real countdown numbers use the hero size.
 */
export function CountdownSlot({ w, ticks }: { w: WorkerSnapshot; ticks: Tick[] }) {
  const last = ticks[ticks.length - 1]
  let main: React.ReactNode
  let sub: React.ReactNode = null
  let tone = 'word'

  if (w.signal_lost) {
    tone = 'lost'
    main = 'No signal'
    const seen = lastSeenClock(ticks, w.worker_id)
    sub = seen ? `last seen ${seen}` : 'waiting for data'
  } else if (isRecovering(w)) {
    tone = 'recovering'
    main = 'Recovering'
    const s = w.core_slope_c_per_h
    const r = w.directed_rest
    const trend = s == null ? '' : ` · ${s <= 0 ? '↓' : '↑'} ${Math.abs(s).toFixed(1)} °C/h`
    sub = r?.until_clear
      ? `${REST_PLACE[r.location]} · ${restCondition(r)}`
      : `${r ? REST_PLACE[r.location] : 'resting'}${trend}`
  } else if (isOverLimit(w)) {
    tone = 'alarm'
    main = 'Over limit'
    const since = overLimitSince(ticks, w)
    sub = since != null && last ? `for ${formatDuration(last.minute - since)}` : 'now'
  } else if (w.forecast_stale) {
    tone = 'muted'
    const p = calibrationProgress(ticks, w.worker_id)
    main = 'Calibrating…'
    sub = <span className="calib-bar"><span style={{ width: `${p * 100}%` }} /></span>
  } else if (w.ttc_min !== null && w.ttc_min <= 0) {
    tone = 'alarm'
    main = 'At limit'
    sub = 'now'
  } else if (w.ttc_min !== null) {
    tone = 'number'
    main = <>{Math.round(w.ttc_min)}<span className="unit">min</span></>
    sub = 'to critical'
  } else {
    // Forecast is clear, but the alert tier is still stepping down (hysteresis).
    tone = 'muted'
    main = w.level === 'NONE' ? 'Safe · 2h+' : 'Easing · 2h+'
  }

  return (
    <div className={`slot tone-${tone}`}>
      <span className="slot-main">{main}</span>
      {sub && <span className="slot-sub">{sub}</span>}
    </div>
  )
}

export function WorkerCard({ w, ticks, selected, onSelect }: {
  w: WorkerSnapshot
  ticks: Tick[]
  selected: boolean
  onSelect: () => void
}) {
  const p = w.profile
  const recovering = isRecovering(w)
  const tags = riskTags(w)
  // One personal reason, not repeating what the tags already say.
  const heading = w.pending_rest_min != null
    ? `Heading to rest in ${Math.max(0, w.pending_rest_min)} min`
    : undefined
  const reason = heading ?? (w.level !== 'NONE' && !w.signal_lost
    ? personalReasons(w).find(
        (r) => !(r.startsWith('Not yet acclimatized') && tags.includes('Not acclimatized'))
          && !(r.startsWith('Age 45+') && tags.includes('Age 45+')),
      )
    : undefined)
  const state = w.signal_lost ? 'lost' : recovering ? 'recovering' : `level-${w.level}`
  const pulse = w.level === 'CRITICAL' && !recovering && !w.signal_lost

  return (
    <button className={`card ${state} ${pulse ? 'pulse' : ''} ${selected ? 'selected' : ''}`} onClick={onSelect}
      aria-label={`${p.name}, ${w.signal_lost ? 'no signal' : LEVEL_LABEL[w.level]}`}>
      <div className="card-head">
        <span className="name">{p.name}</span>
        <span className="role">{p.role}</span>
        {w.signal_lost
          ? <span className="level-chip level-LOST">NO SIGNAL</span>
          : recovering
            ? <span className="level-chip level-RECOVERING">RESTING</span>
            : w.level !== 'NONE' && <span className={`level-chip level-${w.level}`}>{LEVEL_LABEL[w.level]}</span>}
      </div>

      <CountdownSlot w={w} ticks={ticks} />

      <Sparkline w={w} ticks={ticks} />

      <div className="card-line">
        Core <b>{fmt(w.core_c, 1)}</b> °C · HR <b>{fmt(w.hr, 0)}</b>
      </div>
      {tags.length > 0 && (
        <div className="card-tags">{tags.map((t) => <span key={t} className="tag risk">{t}</span>)}</div>
      )}
      {reason && <div className="card-reason">{reason}</div>}
    </button>
  )
}
