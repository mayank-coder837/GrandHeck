import { useCallback, useEffect, useState } from 'react'
import { control } from '../useGateway'
import type { RunState } from '../types'

export interface Toast { id: number; text: string }

export function useToasts() {
  const [toasts, setToasts] = useState<Toast[]>([])
  const push = useCallback((text: string) => {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t.slice(-2), { id, text }])
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 2400)
  }, [])
  return { toasts, push }
}

export function Toasts({ toasts }: { toasts: Toast[] }) {
  return (
    <div className="toasts" aria-live="polite">
      {toasts.map((t) => <div key={t.id} className="toast">{t.text}</div>)}
    </div>
  )
}

export const SHORTCUTS: [string, string][] = [
  ['H', 'Heat surge'],
  ['S', 'Heavy work, no rest (selected or first non-critical worker)'],
  ['D', 'Sensor dropout (selected or first non-critical worker)'],
  ['R', 'Send selected worker to rest'],
  ['N', 'New shift: normal hot day'],
  ['B', 'New shift: heat building'],
  ['G', 'Compare with true core temp (in the detail view)'],
  ['P', 'Presentation mode (larger text for a projector)'],
  ['T', 'Switch dark / light theme'],
  ['Space', 'Pause / resume'],
  ['1–5', 'Speed'],
  ['← →', 'Previous / next worker (detail view)'],
  ['Esc', 'Close detail view'],
  ['? or /', 'Show this list'],
]

export function CheatSheet({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])
  return (
    <div className="overlay center" onClick={onClose}>
      <div className="sheet" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Keyboard shortcuts">
        <h2>Keyboard shortcuts</h2>
        <dl>{SHORTCUTS.map(([k, v]) => <div key={k}><dt><kbd>{k}</kbd></dt><dd>{v}</dd></div>)}</dl>
      </div>
    </div>
  )
}

/** Small floating "Demo" button that opens the presenter's controls. */
export function DemoControls({ state, targetId, workerName, onToast, presentation, onTogglePresentation, onShowShortcuts }: {
  state: RunState
  targetId: string | null
  workerName: (id: string) => string
  onToast: (text: string) => void
  presentation: boolean
  onTogglePresentation: () => void
  onShowShortcuts: () => void
}) {
  const [open, setOpen] = useState(false)
  const [startHour, setStartHour] = useState(7)
  const [picked, setPicked] = useState<string>(state.profiles[0]?.worker_id ?? 'W1')
  const worker = targetId ?? picked
  const act = (body: Record<string, unknown>, toast: string) => { control(body); onToast(toast) }

  return (
    <>
      <button className="demo-fab" onClick={() => setOpen(!open)} aria-expanded={open} title="Demo controls (press ? for shortcuts)">
        Demo {state.paused ? '⏸' : ''}
      </button>
      {open && (
        <div className="demo-drawer" role="dialog" aria-label="Demo controls">
          <div className="drawer-row">
            <span className="drawer-label">New shift</span>
            {Object.entries(state.weather_profiles).map(([key, label]) => (
              <button key={key} className="btn" onClick={() => act({ action: 'reset', weather: key, start_hour: startHour }, `New shift: ${label}`)}>
                {label}
              </button>
            ))}
            <select value={startHour} onChange={(e) => setStartHour(Number(e.target.value))} aria-label="Shift start">
              {[7, 9, 11, 12, 13].map((h) => <option key={h} value={h}>from {String(h).padStart(2, '0')}:00</option>)}
            </select>
          </div>
          <div className="drawer-row">
            <span className="drawer-label">Live events</span>
            <button className="btn" onClick={() => act({ action: 'weather', weather: 'afternoon_build' }, 'Heat surge triggered')}>Heat surge</button>
            <select value={worker} disabled={targetId !== null} onChange={(e) => setPicked(e.target.value)} aria-label="Worker">
              {state.profiles.map((p) => <option key={p.worker_id} value={p.worker_id}>{p.name}</option>)}
            </select>
            <button className="btn" onClick={() => act({ action: 'spike', worker_id: worker }, `Heavy work, no rest: ${workerName(worker)}`)}>Heavy work, no rest</button>
            <button className="btn" onClick={() => act({ action: 'dropout', worker_id: worker }, `Sensor dropout: ${workerName(worker)}`)}>Sensor dropout</button>
            <button className="btn" onClick={() => act({ action: 'rest', worker_id: worker }, `Sent to rest: ${workerName(worker)}`)}>Send to rest</button>
          </div>
          <div className="drawer-row">
            <span className="drawer-label">Speed</span>
            {state.speeds.map((s) => (
              <button key={s} className={`btn ${s === state.speed ? 'active' : ''}`} onClick={() => act({ action: 'speed', speed: s }, `Speed ${s}×`)}>{s}×</button>
            ))}
            <button className="btn" onClick={() => act({ action: state.paused ? 'resume' : 'pause' }, state.paused ? 'Resumed' : 'Paused')}>
              {state.paused ? '▶ Resume' : '⏸ Pause'}
            </button>
            {state.paused && <button className="btn" onClick={() => control({ action: 'step' })}>+1 min</button>}
          </div>
          <div className="drawer-row">
            <span className="drawer-label">Rest</span>
            <select value={state.rest_location} aria-label="Where directed rests happen"
              onChange={(e) => act({ action: 'rest_location', location: e.target.value }, `Rest location: ${e.target.value === 'cooled' ? 'cooled shelter' : 'shade'}`)}>
              <option value="cooled">in a cooled shelter</option>
              <option value="shade">in shade</option>
            </select>
            <label className="toggle">
              <input type="checkbox" checked={state.auto_rest_on_ack}
                onChange={(e) => act({ action: 'auto_rest', enabled: e.target.checked }, e.target.checked ? 'Auto-rest on acknowledge: on' : 'Auto-rest on acknowledge: off')} />
              Acknowledging a Critical sends the worker to rest
            </label>
          </div>
          <div className="drawer-row">
            <span className="drawer-label">Display</span>
            <label className="toggle">
              <input type="checkbox" checked={presentation} onChange={onTogglePresentation} />
              Presentation mode (P)
            </label>
          </div>
          <div className="drawer-foot">
            <button className="btn link" onClick={onShowShortcuts}>Keyboard shortcuts (? or /)</button>
          </div>
        </div>
      )}
    </>
  )
}
