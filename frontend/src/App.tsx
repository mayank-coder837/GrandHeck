import { useState } from 'react'
import { AlertFeed } from './components/AlertFeed'
import { ControlPanel } from './components/ControlPanel'
import { CrewBanner } from './components/CrewBanner'
import { CrewGrid, useStableRiskOrder } from './components/CrewGrid'
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
              <WorkerCard w={byId[id]} horizon={state?.thresholds.horizon_min ?? 120}
                selected={id === selected}
                onSelect={() => setSelected(id === selected ? null : id)} />
            )}
          </CrewGrid>
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
