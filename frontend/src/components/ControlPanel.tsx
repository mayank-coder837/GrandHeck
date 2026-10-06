import { useState } from 'react'
import { control } from '../useGateway'
import type { RunState } from '../types'

export function ControlPanel({ state, selectedId }: { state: RunState; selectedId: string | null }) {
  const [startHour, setStartHour] = useState(7)
  const [target, setTarget] = useState<string>('W1')
  const worker = selectedId ?? target

  return (
    <footer className="controls">
      <div className="group">
        <div className="group-title">New shift</div>
        {Object.entries(state.weather_profiles).map(([key, label]) => (
          <button key={key} onClick={() => control({ action: 'reset', weather: key, start_hour: startHour })}>
            {label}
          </button>
        ))}
        <select value={startHour} onChange={(e) => setStartHour(Number(e.target.value))} title="Shift start time">
          {[7, 9, 11, 12, 13].map((h) => <option key={h} value={h}>from {String(h).padStart(2, '0')}:00</option>)}
        </select>
      </div>

      <div className="group">
        <div className="group-title">Live events</div>
        <button className="event" onClick={() => control({ action: 'weather', weather: 'afternoon_build' })}>
          Heat surge now
        </button>
        <select value={worker} onChange={(e) => setTarget(e.target.value)} disabled={selectedId !== null}
          title={selectedId ? 'Using the selected worker' : 'Worker for events'}>
          {state.profiles.map((p) => <option key={p.worker_id} value={p.worker_id}>{p.name}</option>)}
        </select>
        <button className="event" onClick={() => control({ action: 'spike', worker_id: worker })}>Heavy work, no rest</button>
        <button className="event" onClick={() => control({ action: 'dropout', worker_id: worker })}>Sensor dropout</button>
        <button className="event calm" onClick={() => control({ action: 'rest', worker_id: worker })}>Send to rest</button>
      </div>

      <div className="group">
        <div className="group-title">Speed (sim min / sec)</div>
        {state.speeds.map((s) => (
          <button key={s} className={s === state.speed ? 'active' : ''} onClick={() => control({ action: 'speed', speed: s })}>
            {s}×
          </button>
        ))}
        <button onClick={() => control({ action: state.paused ? 'resume' : 'pause' })}>
          {state.paused ? '▶ Resume' : '⏸ Pause'}
        </button>
        {state.paused && <button onClick={() => control({ action: 'step' })}>+1 min</button>}
      </div>
    </footer>
  )
}
