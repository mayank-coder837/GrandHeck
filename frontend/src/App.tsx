import { useState } from 'react'
import { AlertFeed } from './components/AlertFeed'
import { ControlPanel } from './components/ControlPanel'
import { TopBar } from './components/TopBar'
import { WorkerCard } from './components/WorkerCard'
import { WorkerDetail } from './components/WorkerDetail'
import { useGateway } from './useGateway'

const LEVEL_RANK = { NONE: 0, ADVISORY: 1, WARNING: 2, CRITICAL: 3 }

export default function App() {
  const { state, ticks, alerts, connected } = useGateway()
  const [selected, setSelected] = useState<string | null>(null)
  const last = ticks[ticks.length - 1]
  const workers = last?.workers ?? []
  const selectedWorker = workers.find((w) => w.worker_id === selected)
  const counts = workers.reduce<Record<string, number>>((acc, w) => {
    acc[w.level] = (acc[w.level] ?? 0) + 1
    return acc
  }, {})
  const worst = workers.reduce((m, w) => Math.max(m, LEVEL_RANK[w.level]), 0)

  return (
    <div className="app">
      <TopBar tick={last} state={state} connected={connected} />

      <main className="main">
        <section className="crew">
          <div className="crew-head">
            <h2>Crew · {workers.length} on shift</h2>
            <div className={`summary worst-${worst}`}>
              {(['CRITICAL', 'WARNING', 'ADVISORY'] as const).map((l) =>
                counts[l] ? <span key={l} className={`level-chip level-${l}`}>{counts[l]} {l}</span> : null,
              )}
              {!counts.CRITICAL && !counts.WARNING && !counts.ADVISORY && workers.length > 0 && (
                <span className="level-chip level-NONE">All OK</span>
              )}
            </div>
          </div>
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
