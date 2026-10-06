import {
  calibrationProgress, formatDuration, isOverLimit, isRecovering, lastSeenClock, overLimitSince,
  personalReasons, riskTags,
} from '../derive'
import { LEVEL_LABEL, fmt } from '../format'
import type { Tick, WorkerSnapshot } from '../types'
import { RedlineMeter } from './RedlineMeter'

/** The one fixed-height slot that says how long until it gets critical. */
export function CountdownSlot({ w, ticks, size = 'card' }: { w: WorkerSnapshot; ticks: Tick[]; size?: 'card' | 'hero' }) {
  const last = ticks[ticks.length - 1]
  let main: React.ReactNode
  let sub: React.ReactNode = null
  let tone = 'level'

  if (w.signal_lost) {
    tone = 'lost'
    main = 'No signal'
    const seen = lastSeenClock(ticks, w.worker_id)
    sub = seen ? `last seen ${seen}` : 'waiting for data'
  } else if (isRecovering(w)) {
    tone = 'recovering'
    main = 'Recovering'
    const s = w.core_slope_c_per_h
    sub = s == null ? 'Resting' : `Resting · ${s <= 0 ? '↓' : '↑'} ${Math.abs(s).toFixed(1)} °C/h`
  } else if (isOverLimit(w)) {
    main = 'OVER LIMIT'
    const since = overLimitSince(ticks, w)
    sub = since != null && last ? `for ${formatDuration(last.minute - since)}` : 'now'
  } else if (w.forecast_stale) {
    tone = 'muted'
    const p = calibrationProgress(ticks, w.worker_id)
    main = <span className="calibrating">Calibrating…</span>
    sub = <span className="calib-bar"><span style={{ width: `${p * 100}%` }} /></span>
  } else if (w.ttc_min !== null && w.ttc_min <= 0) {
    main = 'AT LIMIT'
    sub = 'now'
  } else if (w.ttc_min !== null) {
    main = <>{Math.round(w.ttc_min)}<span className="unit">min</span></>
    sub = 'to critical'
  } else {
    tone = 'muted'
    main = <span className="safe">{w.level === 'NONE' ? 'Safe' : 'No crossing'}</span>
    sub = 'next 2h+'
  }

  return (
    <div className={`slot slot-${size} tone-${tone}`}>
      <div className="slot-main">{main}</div>
      <div className="slot-sub">{sub}</div>
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
  const reason = personalReasons(w).find(
    (r) => !(r.startsWith('Not yet acclimatized') && tags.includes('Not acclimatized'))
      && !(r.startsWith('Age 45+') && tags.includes('Age 45+')),
  )
  const state = w.signal_lost ? 'lost' : recovering ? 'recovering' : `level-${w.level}`
  const pulse = w.level === 'CRITICAL' && !recovering && !w.signal_lost

  return (
    <button className={`card ${state} ${pulse ? 'pulse' : ''} ${selected ? 'selected' : ''}`} onClick={onSelect}
      aria-label={`${p.name}, ${w.signal_lost ? 'no signal' : LEVEL_LABEL[w.level]}`}>
      <div className="card-head">
        <div className="who">
          <div className="name">{p.name}</div>
          <div className="role">{p.role}</div>
        </div>
        {w.signal_lost
          ? <span className="level-chip level-LOST">NO SIGNAL</span>
          : recovering
            ? <span className="level-chip level-RECOVERING">RESTING</span>
            : w.level !== 'NONE' && <span className={`level-chip level-${w.level}`}>{LEVEL_LABEL[w.level]}</span>}
      </div>

      <CountdownSlot w={w} ticks={ticks} />

      <RedlineMeter w={w} recovering={recovering} />

      <div className="card-line">
        Core <b>{fmt(w.core_c, 1)}</b> °C · HR <b>{fmt(w.hr, 0)}</b>
      </div>
      <div className="card-tags">
        {tags.map((t) => <span key={t} className="tag">{t}</span>)}
      </div>
      <div className="card-reason">{reason ?? ''}</div>
    </button>
  )
}
