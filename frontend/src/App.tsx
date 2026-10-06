import { useState } from 'react'
import { AlertFeed, type AckMap } from './components/AlertFeed'
import { ControlPanel } from './components/ControlPanel'
import { CrewBanner } from './components/CrewBanner'
import { CrewGrid, useStableRiskOrder } from './components/CrewGrid'
import { TopBar } from './components/TopBar'
import { WorkerCard } from './components/WorkerCard'
import { WorkerDetail } from './components/WorkerDetail'
import { control, useGateway } from './useGateway'

export default function App() {
  const { state, ticks, alerts, connected } = useGateway()
  const [selected, setSelected] = useState<string | null>(null)
  const [acks, setAcks] = useState<AckMap>({})
  const [showTruth, setShowTruth] = useState(false)
  const acknowledge = (workerId: string, ts: string) => setAcks((a) => ({ ...a, [workerId]: ts }))
  const sendToRest = (workerId: string) => control({ action: 'rest', worker_id: workerId })
  const last = ticks[ticks.length - 1]
  const workers = last?.workers ?? []
  const selectedWorker = workers.find((w) => w.worker_id === selected)
  const order = useStableRiskOrder(workers)
  const byId = Object.fromEntries(workers.map((w) => [w.worker_id, w]))

  return (
    <div className="app">
      <TopBar tick={last} state={state} connected={connected}
        historyMinutes={ticks.length ? last.minute - ticks[0].minute : 0} />

      <main className="main">
        <section className="crew">
          <CrewBanner workers={workers} site={last?.site} />
          <CrewGrid order={order}>
            {(id) => byId[id] && (
              <WorkerCard w={byId[id]} ticks={ticks}
                selected={id === selected}
                onSelect={() => setSelected(id === selected ? null : id)} />
            )}
          </CrewGrid>
        </section>

        <AlertFeed alerts={alerts} workers={workers} acks={acks} onAck={acknowledge}
          onRest={sendToRest} onSelect={setSelected} />
      </main>

      {selectedWorker && state && last && (
        <WorkerDetail worker={selectedWorker} ticks={ticks} alerts={alerts} utcOffsetH={state.site.utc_offset_h}
          acked={(() => {
            const lastAlert = [...alerts].reverse().find((a) => a.worker_id === selectedWorker.worker_id
              && ['escalated', 'renotify', 'signal_lost'].includes(a.kind))
            return !!lastAlert && acks[selectedWorker.worker_id] === lastAlert.ts
          })()}
          showTruth={showTruth} onToggleTruth={() => setShowTruth((v) => !v)}
          onAck={(ts) => acknowledge(selectedWorker.worker_id, ts)}
          onRest={() => sendToRest(selectedWorker.worker_id)}
          onClose={() => setSelected(null)}
          onPrev={() => setSelected(order[(order.indexOf(selectedWorker.worker_id) - 1 + order.length) % order.length])}
          onNext={() => setSelected(order[(order.indexOf(selectedWorker.worker_id) + 1) % order.length])} />
      )}

      {state && <ControlPanel state={state} selectedId={selected} />}
    </div>
  )
}
