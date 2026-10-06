import { useMemo, useState } from 'react'
import {
  CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { LEVEL_LABEL, clockAt, fmt } from '../format'
import type { Tick, WorkerSnapshot } from '../types'

const C = {
  core: '#38bdf8',
  truth: '#94a3b8',
  forecast: '#fb923c',
  limit: '#ef4444',
  hr: '#f472b6',
  psi: '#a78bfa',
  wbgt: '#facc15',
  grid: '#1e293b',
  axis: '#94a3b8',
}

interface Row {
  minute: number
  core?: number | null
  truth?: number | null
  forecast?: number | null
  risk?: number | null
  hr?: number | null
  psi?: number | null
  wbgt?: number | null
}

export function WorkerDetail({ worker, ticks, utcOffsetH, onClose }: {
  worker: WorkerSnapshot
  ticks: Tick[]
  utcOffsetH: number
  onClose: () => void
}) {
  const [showTruth, setShowTruth] = useState(false)
  const id = worker.worker_id
  const last = ticks[ticks.length - 1]

  const rows = useMemo<Row[]>(() => {
    const out: Row[] = ticks.map((t) => {
      const w = t.workers.find((x) => x.worker_id === id)
      return {
        minute: t.minute,
        core: w?.point.core_c ?? null,
        truth: t.truth?.[id]?.core_c ?? null,
        hr: w?.point.hr ?? null,
        psi: w?.point.psi ?? null,
        wbgt: t.site.wbgt_c,
      }
    })
    if (last && !worker.forecast_stale && !worker.signal_lost) {
      const future = new Map<number, Row>()
      const at = (k: number) => {
        if (k === 0) return out[out.length - 1]
        if (!future.has(k)) future.set(k, { minute: last.minute + k })
        return future.get(k)!
      }
      worker.forecast_line.forEach(([k, v]) => { at(k).forecast = v })
      worker.risk_line.forEach(([k, v]) => { at(k).risk = v })
      out.push(...[...future.values()].sort((a, b) => a.minute - b.minute))
    }
    return out
  }, [ticks, id, worker, last])

  if (!last) return null
  const tickFmt = (m: number) => clockAt(last.ts, last.minute, m, utcOffsetH)
  const xDomain: [number, number] = [rows[0]?.minute ?? 0, rows[rows.length - 1]?.minute ?? 1]
  const p = worker.profile
  const commonX = (
    <XAxis dataKey="minute" type="number" domain={xDomain} tickFormatter={tickFmt}
      stroke={C.axis} tick={{ fontSize: 13 }} minTickGap={40} />
  )

  return (
    <section className={`detail level-${worker.level}`}>
      <div className="detail-head">
        <div>
          <h2>{p.name} <span className="muted">· {p.role}</span></h2>
          <div className="muted">
            {p.acclimatized ? 'Acclimatized' : 'Not acclimatized'} · {p.workload} work · age {p.age} ·
            core limit {worker.core_limit_c.toFixed(1)} °C · WBGT limit {worker.wbgt_limit_c.toFixed(1)} °C
            {' '}({p.acclimatized ? 'NIOSH REL' : 'NIOSH RAL'})
          </div>
        </div>
        <div className="detail-kpis">
          <div><div className="label">Status</div><div className={`level-chip level-${worker.level}`}>{LEVEL_LABEL[worker.level]}</div></div>
          <div>
            <div className="label">Time to critical · earliest likely</div>
            <div className="kpi">{worker.signal_lost ? 'no signal' : worker.ttc_min === null ? '> 120' : Math.round(worker.ttc_min)}<small> min</small></div>
          </div>
          <div>
            <div className="label">Expected</div>
            <div className="kpi">{worker.signal_lost || worker.ttc_expected_min === null ? '—' : Math.round(worker.ttc_expected_min)}<small> min</small></div>
          </div>
          <div><div className="label">Core trend</div><div className="kpi">{fmt(worker.core_slope_c_per_h, 1)}<small> °C/h</small></div></div>
          <div><div className="label">Above WBGT limit</div><div className="kpi">{worker.exposure_total_min}<small> min</small></div></div>
        </div>
        <button className="close" onClick={onClose} aria-label="Close">✕</button>
      </div>

      {worker.reasons.length > 0 && (
        <div className="why big-why"><b>Contributing factors:</b> {worker.reasons.join(' · ')}</div>
      )}

      <div className="charts">
        <div className="chart wide">
          <div className="chart-title">
            Estimated core temperature (ECTemp, from heart rate) and forecast
            <label className="toggle">
              <input type="checkbox" checked={showTruth} onChange={(e) => setShowTruth(e.target.checked)} />
              show simulator ground truth
            </label>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={rows} margin={{ top: 8, right: 24, bottom: 0, left: 0 }}>
              <CartesianGrid stroke={C.grid} />
              {commonX}
              <YAxis domain={[36.8, 39.2]} stroke={C.axis} tick={{ fontSize: 13 }} unit="°" width={48} />
              <Tooltip labelFormatter={(m) => tickFmt(Number(m))} contentStyle={{ background: '#0f172a', border: '1px solid #334155' }} />
              <ReferenceLine y={worker.core_limit_c} stroke={C.limit} strokeWidth={2} strokeDasharray="6 4"
                label={{ value: `danger ${worker.core_limit_c.toFixed(1)}°C`, fill: C.limit, position: 'insideTopLeft', fontSize: 13 }} />
              <ReferenceLine x={last.minute} stroke="#475569" />
              <Line dataKey="core" name="Core (est.)" stroke={C.core} strokeWidth={3} dot={false} isAnimationActive={false} connectNulls={false} />
              <Line dataKey="forecast" name="Forecast" stroke={C.forecast} strokeWidth={3} strokeDasharray="8 5" dot={false} isAnimationActive={false} />
              {worker.risk_line.length > 0 && (
                <Line dataKey="risk" name="Risk edge (warns when it hits the limit)" stroke={C.forecast} strokeWidth={1.5}
                  strokeDasharray="2 4" dot={false} isAnimationActive={false} />
              )}
              {showTruth && <Line dataKey="truth" name="Ground truth (sim)" stroke={C.truth} strokeWidth={1.5} dot={false} isAnimationActive={false} />}
              <Legend />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="chart">
          <div className="chart-title">Heart rate and PSI</div>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={rows} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid stroke={C.grid} />
              {commonX}
              <YAxis yAxisId="hr" domain={[50, 190]} stroke={C.hr} tick={{ fontSize: 13 }} width={40} />
              <YAxis yAxisId="psi" orientation="right" domain={[0, 10]} stroke={C.psi} tick={{ fontSize: 13 }} width={30} />
              <Tooltip labelFormatter={(m) => tickFmt(Number(m))} contentStyle={{ background: '#0f172a', border: '1px solid #334155' }} />
              <ReferenceLine yAxisId="psi" y={7} stroke={C.psi} strokeDasharray="4 4" />
              <Line yAxisId="hr" dataKey="hr" name="HR (bpm)" stroke={C.hr} dot={false} isAnimationActive={false} />
              <Line yAxisId="psi" dataKey="psi" name="PSI" stroke={C.psi} strokeWidth={2} dot={false} isAnimationActive={false} />
              <Legend />
            </LineChart>
          </ResponsiveContainer>
        </div>

        <div className="chart">
          <div className="chart-title">WBGT vs. this worker's limit</div>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
              <CartesianGrid stroke={C.grid} />
              {commonX}
              <YAxis domain={['dataMin - 2', 'dataMax + 2']} stroke={C.axis} tick={{ fontSize: 13 }} unit="°" width={44}
                tickFormatter={(v) => Number(v).toFixed(0)} />
              <Tooltip labelFormatter={(m) => tickFmt(Number(m))} contentStyle={{ background: '#0f172a', border: '1px solid #334155' }} />
              <ReferenceLine y={worker.wbgt_limit_c} stroke={C.limit} strokeDasharray="6 4"
                label={{ value: 'limit', fill: C.limit, position: 'insideTopLeft', fontSize: 13 }} />
              <Line dataKey="wbgt" name="WBGT" stroke={C.wbgt} strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </section>
  )
}
