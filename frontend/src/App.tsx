import { useState } from 'react'
import { AlertFeed } from './components/AlertFeed'
import { ControlPanel } from './components/ControlPanel'
import { CrewBanner } from './components/CrewBanner'
import { TopBar } from './components/TopBar'
import { WorkerCard } from './components/WorkerCard'
import { WorkerDetail } from './components/WorkerDetail'
import { useGateway } from './useGateway'

export default function App() {
  const { state, ticks, alerts, connected } = useGateway()
  const [selected, setSelected] = useState<string | null>(null)
  const last = ticks[ticks.length - 1]
  const workers = last?.workers ?? []
  const selectedWorker = workers.find((w) => w.worker_id === selected)

  return (
    <div className="app">
      <TopBar tick={last} state={state} connected={connected}
        historyMinutes={ticks.length ? last.minute - ticks[0].minute : 0} />

      <main className="main">
        <section className="crew">
          <CrewBanner workers={workers} site={last?.site} />
          <div className="grid">
            {workers.map((w) => (
              <WorkerCard key={w.worker_id} w={w} horizon={state?.thresholds.horizon_min ?? 120}
                selected={w.worker_id === selected}
                onSelect={() => setSelected(w.worker_id === selected ? null : w.worker_id)} />
            ))}
          </div>
          {selectedWorker && state && (
            <WorkerDetail worker={selectedWorker} ticks={ticks} utcOffsetH={state.site.utc_offset_h}
              onClose={() => setSelected(null)} />
          )}
        </section>

        <AlertFeed alerts={alerts} profiles={state?.profiles ?? []} onSelect={setSelected} />
      </main>

      {state && <ControlPanel state={state} selectedId={selected} />}
    </div>
  )
}
