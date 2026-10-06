import { useEffect, useRef, useState } from 'react'
import { AlertFeed, type AckMap } from './components/AlertFeed'
import { CrewBanner } from './components/CrewBanner'
import { CrewGrid, useStableRiskOrder } from './components/CrewGrid'
import { CheatSheet, DemoControls, Toasts, useToasts } from './components/DemoControls'
import { TopBar } from './components/TopBar'
import { WorkerCard } from './components/WorkerCard'
import { WorkerDetail } from './components/WorkerDetail'
import type { Alert } from './types'
import { control, useGateway } from './useGateway'

const ACTIONABLE = new Set<Alert['kind']>(['escalated', 'renotify', 'signal_lost'])

export default function App() {
  const { state, ticks, alerts, connected } = useGateway()
  const [selected, setSelected] = useState<string | null>(null)
  const [acks, setAcks] = useState<AckMap>({})
  const [showTruth, setShowTruth] = useState(false)
  const [cheatSheet, setCheatSheet] = useState(false)
  const { toasts, push: toast } = useToasts()

  const last = ticks[ticks.length - 1]
  const workers = last?.workers ?? []
  const byId = Object.fromEntries(workers.map((w) => [w.worker_id, w]))
  const order = useStableRiskOrder(workers)
  const selectedWorker = selected ? byId[selected] : undefined
  const name = (id: string) => byId[id]?.profile.name ?? id

  const latestAlert = (id: string) => [...alerts].reverse().find((a) => a.worker_id === id && ACTIONABLE.has(a.kind))
  const acknowledge = (id: string, ts: string) => setAcks((a) => ({ ...a, [id]: ts }))
  const sendToRest = (id: string) => { control({ action: 'rest', worker_id: id }); toast(`Sent to rest: ${name(id)}`) }
  const step = (delta: number) => {
    if (!selected) return
    setSelected(order[(order.indexOf(selected) + delta + order.length) % order.length])
  }

  // Keyboard shortcuts for the presenter. Read live values through a ref so the
  // listener is attached once.
  const live = useRef({ state, selected, order, byId })
  live.current = { state, selected, order, byId }
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement || e.target instanceof HTMLTextAreaElement) return
      const { state: st, selected: sel, order: ord, byId: ids } = live.current
      if (!st) return
      const firstCalm = ord.find((id) => ids[id] && ids[id].level !== 'CRITICAL' && !ids[id].signal_lost)
      const target = sel ?? firstCalm ?? null
      const nm = (id: string) => ids[id]?.profile.name ?? id
      const k = e.key.length === 1 ? e.key.toLowerCase() : e.key
      if (k === 'h') { control({ action: 'weather', weather: 'afternoon_build' }); toast('Heat surge triggered') }
      else if (k === 's' && target) { control({ action: 'spike', worker_id: target }); toast(`Heavy work, no rest: ${nm(target)}`) }
      else if (k === 'd' && target) { control({ action: 'dropout', worker_id: target }); toast(`Sensor dropout: ${nm(target)}`) }
      else if (k === 'r') {
        if (sel) { control({ action: 'rest', worker_id: sel }); toast(`Sent to rest: ${nm(sel)}`) }
        else toast('Select a worker first')
      }
      else if (k === 'n') { control({ action: 'reset', weather: 'normal', start_hour: 7 }); toast('New shift: normal hot day') }
      else if (k === 'b') { control({ action: 'reset', weather: 'afternoon_build', start_hour: 7 }); toast('New shift: heat building') }
      else if (k === 'g') { if (sel) setShowTruth((v) => !v) }
      else if (k === ' ') { e.preventDefault(); control({ action: st.paused ? 'resume' : 'pause' }); toast(st.paused ? 'Resumed' : 'Paused') }
      else if (/^[1-5]$/.test(k)) {
        const speed = st.speeds[Number(k) - 1]
        if (speed !== undefined) { control({ action: 'speed', speed }); toast(`Speed ${speed}×`) }
      }
      else if (k === '?') setCheatSheet((v) => !v)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [toast])

  const detailAlert = selectedWorker ? latestAlert(selectedWorker.worker_id) : undefined

  return (
    <div className="app">
      <TopBar tick={last} state={state} connected={connected}
        historyMinutes={ticks.length ? last.minute - ticks[0].minute : 0} />

      <main className="main">
        <section className="crew">
          <CrewBanner workers={workers} site={last?.site} />
          <CrewGrid order={order}>
            {(id) => byId[id] && (
              <WorkerCard w={byId[id]} ticks={ticks} selected={id === selected} onSelect={() => setSelected(id)} />
            )}
          </CrewGrid>
        </section>

        <AlertFeed alerts={alerts} workers={workers} acks={acks} onAck={acknowledge}
          onRest={sendToRest} onSelect={setSelected} />
      </main>

      {selectedWorker && last && (
        <WorkerDetail worker={selectedWorker} ticks={ticks} alerts={alerts}
          acked={!!detailAlert && acks[selectedWorker.worker_id] === detailAlert.ts}
          showTruth={showTruth} onToggleTruth={() => setShowTruth((v) => !v)}
          onAck={(ts) => acknowledge(selectedWorker.worker_id, ts)}
          onRest={() => sendToRest(selectedWorker.worker_id)}
          onClose={() => setSelected(null)} onPrev={() => step(-1)} onNext={() => step(1)} />
      )}

      {state && <DemoControls state={state} targetId={selected} workerName={name} onToast={toast} />}
      {cheatSheet && <CheatSheet onClose={() => setCheatSheet(false)} />}
      <Toasts toasts={toasts} />
    </div>
  )
}
