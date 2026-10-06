import { isRecovering } from '../derive'
import { LEVEL_LABEL, fmt } from '../format'
import { RedlineMeter } from './RedlineMeter'
import type { WorkerSnapshot } from '../types'

function Countdown({ w, horizon }: { w: WorkerSnapshot; horizon: number }) {
  if (w.signal_lost) return <div className="ttc lost">NO SIGNAL</div>
  if (w.forecast_stale) return <div className="ttc muted">learning…</div>
  if (w.ttc_min === null) return <div className="ttc ok">&gt; {horizon} min</div>
  if (w.ttc_min <= 0) return <div className="ttc now">AT LIMIT</div>
  return (
    <div className="ttc">
      {Math.round(w.ttc_min)}
      <span className="unit"> min</span>
    </div>
  )
}

export function WorkerCard({ w, horizon, selected, onSelect }: {
  w: WorkerSnapshot
  horizon: number
  selected: boolean
  onSelect: () => void
}) {
  const p = w.profile
  return (
    <button
      className={`card level-${w.level} ${w.signal_lost ? 'signal-lost' : ''} ${selected ? 'selected' : ''}`}
      onClick={onSelect}
    >
      <div className="card-head">
        <div>
          <div className="name">{p.name}</div>
          <div className="role">{p.role}</div>
        </div>
        <div className={`level-chip level-${w.level}`}>{LEVEL_LABEL[w.level]}</div>
      </div>

      <div className="tags">
        <span className={`tag ${p.acclimatized ? '' : 'tag-risk'}`}>{p.acclimatized ? 'Acclimatized' : 'Not acclimatized'}</span>
        <span className={`tag ${w.workload_observed === 'heavy' ? 'tag-risk' : ''}`}
          title={w.workload_observed !== p.workload ? `Assigned ${p.workload}; accelerometer shows ${w.workload_observed}` : 'Workload'}>
          {w.workload_observed !== p.workload ? `now ${w.workload_observed}` : p.workload}
        </span>
        <span className={`tag ${p.age_band === '45+' ? 'tag-risk' : ''}`}>age {p.age_band}</span>
        {w.resting && !w.signal_lost && <span className="tag tag-rest">resting</span>}
      </div>

      <div className="ttc-label">Time to critical · if unchanged</div>
      <Countdown w={w} horizon={horizon} />

      <RedlineMeter w={w} recovering={isRecovering(w)} />

      <div className="metrics">
        <div title={`Danger limit ${w.core_limit_c.toFixed(1)} °C`}><span className="k">Core</span><span className="v">{fmt(w.core_c, 1, '°C')}</span></div>
        <div><span className="k">HR</span><span className="v">{fmt(w.hr, 0)}</span></div>
        <div><span className="k">PSI</span><span className="v">{fmt(w.psi, 1)}</span></div>
        <div><span className="k">No rest</span><span className="v">{w.minutes_since_rest}<small>m</small></span></div>
      </div>
      {w.level !== 'NONE' && !w.signal_lost && w.reasons.length > 0 && (
        <div className="card-why">{w.reasons[0]}</div>
      )}
    </button>
  )
}
