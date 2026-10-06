import { useEffect, useMemo, useState } from 'react'
import {
  Area, CartesianGrid, ComposedChart, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from 'recharts'
import { actionHeadline, isRecovering, orderedReasons, riskTags } from '../derive'
import { LEVEL_LABEL, fmt } from '../format'
import type { Alert, Tick, WorkerSnapshot } from '../types'
import { AXIS_TICK, CHART, TOOLTIP_STYLE, domainWithPadding, makeClock, rollingMean } from '../chartUtils'
import { CountdownSlot } from './WorkerCard'

const HISTORY_WINDOW_MIN = 120
const WBGT_SMOOTH_MIN = 5
const NOWCAST_NOTE_THRESHOLD_C = 0.1
const C = CHART

export function WorkerDetail({
  worker, ticks, alerts, acked, showTruth, onToggleTruth, onAck, onRest, onClose, onPrev, onNext,
}: {
  worker: WorkerSnapshot
  ticks: Tick[]
  alerts: Alert[]
  acked: boolean
  showTruth: boolean
  onToggleTruth: () => void
  onAck: (ts: string) => void
  onRest: () => void
  onClose: () => void
  onPrev: () => void
  onNext: () => void
}) {
  const [protocol, setProtocol] = useState(false)
  const [details, setDetails] = useState(false)
  const id = worker.worker_id
  const last = ticks[ticks.length - 1]
  const clock = makeClock(last)
  const now = last.minute
  const start = Math.max(ticks[0].minute, now - HISTORY_WINDOW_MIN)
  const limit = worker.core_limit_c

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return
      if (e.key === 'Escape') onClose()
      else if (e.key === 'ArrowLeft') onPrev()
      else if (e.key === 'ArrowRight') onNext()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose, onPrev, onNext])

  // ----- data -----
  const history = useMemo(() => ticks.filter((t) => t.minute >= start).map((t) => {
    const w = t.workers.find((x) => x.worker_id === id)
    return {
      minute: t.minute,
      core: w?.point.core_c ?? null,
      truth: t.truth?.[id]?.core_c ?? null,
      hr: w?.point.hr ?? null,
      psi: w?.point.psi ?? null,
      wbgtRaw: t.site.wbgt_c,
    }
  }), [ticks, id, start])

  const smallRows = useMemo(() => {
    const smooth = rollingMean(history.map((r) => r.wbgtRaw), WBGT_SMOOTH_MIN)
    return history.map((r, i) => ({ ...r, wbgt: smooth[i] }))
  }, [history])

  const showForecast = !worker.forecast_stale && !worker.signal_lost && worker.forecast_line.length > 0
  const nowcast = worker.forecast_line.find(([k]) => k === 0)?.[1] ?? null
  const coreRows = useMemo(() => {
    type Row = { minute: number; core?: number | null; truth?: number | null; forecast?: number; band?: [number, number] }
    const rows: Row[] = history.map(({ minute, core, truth }) => ({ minute, core, truth }))
    if (showForecast && rows.length) {
      // The forecast is drawn from the current estimate, so the line starts exactly at "now".
      const est = worker.core_c
      rows[rows.length - 1].forecast = est
      rows[rows.length - 1].band = [est, est]
      const risk = new Map(worker.risk_line.map(([k, v]) => [k, v]))
      for (const [k, v] of worker.forecast_line) {
        if (k <= 0) continue
        const r = risk.get(k) ?? v
        rows.push({ minute: now + k, forecast: v, band: [Math.min(v, r), Math.max(v, r)] })
      }
    }
    return rows
  }, [history, showForecast, worker, now])

  const end = coreRows[coreRows.length - 1]?.minute ?? now
  const coreValues = [limit, ...coreRows.flatMap((r) => [
    r.core, showTruth ? r.truth : null, r.forecast, ...(r.band ?? []),
  ]).filter((v): v is number => v != null)]
  const coreDomain = domainWithPadding(coreValues, 0.2)

  const wbgtVals = smallRows.map((r) => r.wbgt).filter((v): v is number => v != null)
  const wbgtDomain = domainWithPadding([...wbgtVals, worker.wbgt_limit_c], 1.0, 1)
  const hrVals = smallRows.map((r) => r.hr).filter((v): v is number => v != null)
  const hrDomain = hrVals.length ? domainWithPadding(hrVals, 8, 10) : [50, 190] as [number, number]

  // ----- header bits -----
  const p = worker.profile
  const recovering = isRecovering(worker)
  const tags = riskTags(worker, 3)
  const latest = [...alerts].reverse().find((a) => a.worker_id === id && ['escalated', 'renotify', 'signal_lost'].includes(a.kind))
  const needsAction = worker.signal_lost || worker.level !== 'NONE'
  const chip = worker.signal_lost ? ['LOST', 'NO SIGNAL'] : recovering ? ['RECOVERING', 'RESTING'] : [worker.level, LEVEL_LABEL[worker.level]]
  const expectedTip = worker.ttc_expected_min == null
    ? 'Expected (central forecast): no crossing within 2 h'
    : `Expected (central forecast): ${Math.round(worker.ttc_expected_min)} min. The countdown uses the earlier, likely-range edge.`
  const slope = worker.core_slope_c_per_h

  const coreXTicks = clock.halfHours(start, end)
  const smallXTicks = clock.halfHours(start, now)
  const axisX = (domainEnd: number, xticks: number[]) => (
    <XAxis dataKey="minute" type="number" domain={[start, domainEnd]} ticks={xticks}
      tickFormatter={clock.label} stroke={C.axis} tick={AXIS_TICK} axisLine={false} tickLine={false} />
  )
  const tooltipLabel = (m: unknown) => clock.label(Number(m))

  return (
    <div className="overlay" onClick={onClose}>
      <aside className={`focus level-${worker.level}`} onClick={(e) => e.stopPropagation()} role="dialog"
        aria-label={`${p.name} details`}>
        {/* ---------- header ---------- */}
        <div className="focus-head">
          <div className="focus-id">
            <div className="focus-title">
              <h2>{p.name}</h2>
              <span className="muted">{p.role}</span>
              {(needsAction || recovering) && <span className={`level-chip level-${chip[0]}`}>{chip[1]}</span>}
            </div>
            <div className="card-tags">{tags.map((t) => <span key={t} className="tag">{t}</span>)}</div>
          </div>
          <div className="focus-nav">
            <button className="btn icon" onClick={onPrev} aria-label="Previous worker" title="Previous (←)">‹</button>
            <button className="btn icon" onClick={onNext} aria-label="Next worker" title="Next (→)">›</button>
            <button className="btn icon" onClick={onClose} aria-label="Close" title="Close (Esc)">✕</button>
          </div>
        </div>

        <div className="focus-kpis">
          <div className="hero-kpi" title={expectedTip}>
            <div className="kpi-label">Time to critical</div>
            <CountdownSlot w={worker} ticks={ticks} />
          </div>
          <div className="kpi">
            <div className="kpi-label">Core temp</div>
            <div className="kpi-value">{fmt(worker.core_c, 1)}<span className="unit">°C</span>
              <span className="kpi-of"> / limit {limit.toFixed(1)} °C</span></div>
          </div>
          <div className="kpi">
            <div className="kpi-label">Core trend</div>
            <div className="kpi-value">{slope == null ? '—' : `${slope > 0 ? '+' : ''}${slope.toFixed(1)}`}<span className="unit">°C/h</span></div>
          </div>
          <div className="kpi">
            <div className="kpi-label">Above heat limit</div>
            <div className="kpi-value">{worker.exposure_total_min}<span className="unit">min</span></div>
          </div>
        </div>

        {needsAction && latest ? (
          <div className={`focus-action level-${chip[0]}`}>
            <div className="focus-action-text">{actionHeadline(latest.action) || 'Check on the worker.'}</div>
            <div className="entry-buttons">
              {recovering
                ? <span className="resting-note">Resting now</span>
                : <button className="btn primary" onClick={onRest}>Send to rest</button>}
              {!acked && <button className="btn" onClick={() => onAck(latest.ts)}>Acknowledge</button>}
              <button className="btn link" onClick={() => setProtocol(!protocol)} aria-expanded={protocol}>
                Full protocol {protocol ? '▾' : '▸'}
              </button>
            </div>
            {protocol && <p className="protocol">{latest.action}</p>}
          </div>
        ) : (
          <div className="focus-action calm">No action needed. Keep the normal work–rest schedule and hydration.</div>
        )}

        {worker.reasons.length > 0 && (
          <div className="focus-why"><b>Why:</b>{' '}
            {orderedReasons(worker.reasons).map((r, i) => (
              <span key={i} className={r.site ? 'muted' : ''}>{i > 0 && ' · '}{r.text}</span>
            ))}
          </div>
        )}

        {/* ---------- main chart ---------- */}
        <div className="chart-block">
          <div className="chart-head">
            <h3>Core temperature (estimated from heart rate)</h3>
            <div className="legend">
              <span><i className="sw line" style={{ background: C.core }} />Estimated core temp</span>
              {showForecast && <span><i className="sw dash" style={{ borderColor: C.forecast }} />Forecast</span>}
              {showForecast && worker.risk_line.length > 0 && <span><i className="sw band" style={{ background: C.band }} />Likely range</span>}
              <span><i className="sw line" style={{ background: C.limit }} />Danger limit</span>
              {showTruth && <span><i className="sw line" style={{ background: C.truth }} />True core temp (sim)</span>}
            </div>
            <label className="toggle small" title="Shortcut: G">
              <input type="checkbox" checked={showTruth} onChange={onToggleTruth} />
              Compare with true core temp (simulation only)
            </label>
          </div>
          <ResponsiveContainer width="100%" height={300}>
            <ComposedChart data={coreRows} margin={{ top: 16, right: 112, bottom: 0, left: 0 }}>
              <CartesianGrid stroke={C.grid} vertical={false} />
              {axisX(end, coreXTicks)}
              <YAxis domain={coreDomain} stroke={C.axis} tick={AXIS_TICK} axisLine={false} tickLine={false} width={48}
                tickFormatter={(v) => `${Number(v).toFixed(1)}°`} allowDataOverflow={false} />
              <Tooltip labelFormatter={tooltipLabel} contentStyle={TOOLTIP_STYLE}
                formatter={(v, name) => Array.isArray(v) ? [`${Number(v[0]).toFixed(2)}–${Number(v[1]).toFixed(2)} °C`, name] : [`${Number(v).toFixed(2)} °C`, name]} />
              <ReferenceArea y1={limit} y2={coreDomain[1]} fill={C.limit} fillOpacity={0.07} ifOverflow="hidden" />
              <ReferenceLine y={limit} stroke={C.limit} strokeWidth={2}
                label={{ value: `Danger ${limit.toFixed(1)} °C`, position: 'right', fill: C.limit, fontSize: 13, fontWeight: 700 }} />
              <ReferenceLine x={now} stroke="#64748b" strokeDasharray="3 3"
                label={{ value: 'now', position: 'top', fill: C.axis, fontSize: 12 }} />
              {showForecast && (
                <Area dataKey="band" name="Likely range" stroke="none" fill={C.band} fillOpacity={0.18} isAnimationActive={false} connectNulls />
              )}
              <Line dataKey="core" name="Estimated core temp" stroke={C.core} strokeWidth={3} dot={false} isAnimationActive={false} connectNulls={false} />
              {showForecast && (
                <Line dataKey="forecast" name="Forecast" stroke={C.forecast} strokeWidth={3} strokeDasharray="8 5" dot={false} isAnimationActive={false} connectNulls />
              )}
              {showTruth && <Line dataKey="truth" name="True core temp (sim)" stroke={C.truth} strokeWidth={1.5} dot={false} isAnimationActive={false} />}
            </ComposedChart>
          </ResponsiveContainer>
          {showForecast && nowcast != null && Math.abs(nowcast - worker.core_c) > NOWCAST_NOTE_THRESHOLD_C && (
            <div className="chart-note">
              Model-corrected current core temp: {nowcast.toFixed(1)} °C. The heart-rate estimate lags when core temperature
              changes fast; the forecast model corrects for that lag.
            </div>
          )}
        </div>

        {/* ---------- small charts ---------- */}
        <div className="small-charts">
          <div className="chart-block">
            <h3>Heart rate (bpm)</h3>
            <ResponsiveContainer width="100%" height={150}>
              <LineChart data={smallRows} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                <CartesianGrid stroke={C.grid} vertical={false} />
                {axisX(now, smallXTicks)}
                <YAxis domain={hrDomain} stroke={C.axis} tick={AXIS_TICK} axisLine={false} tickLine={false} width={40} />
                <Tooltip labelFormatter={tooltipLabel} contentStyle={TOOLTIP_STYLE} formatter={(v) => [`${Number(v).toFixed(0)} bpm`, 'Heart rate']} />
                <Line dataKey="hr" stroke={C.hr} strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-block">
            <h3>Strain index (PSI 0–10)</h3>
            <ResponsiveContainer width="100%" height={150}>
              <LineChart data={smallRows} margin={{ top: 8, right: 84, bottom: 0, left: 0 }}>
                <CartesianGrid stroke={C.grid} vertical={false} />
                {axisX(now, smallXTicks)}
                <YAxis domain={[0, 10]} ticks={[0, 3, 5, 7, 10]} stroke={C.axis} tick={AXIS_TICK} axisLine={false} tickLine={false} width={28} />
                <Tooltip labelFormatter={tooltipLabel} contentStyle={TOOLTIP_STYLE} formatter={(v) => [Number(v).toFixed(1), 'PSI']} />
                <ReferenceLine y={7} stroke={C.psi} strokeDasharray="4 4"
                  label={{ value: 'High strain 7', position: 'right', fill: C.psi, fontSize: 12 }} />
                <Line dataKey="psi" stroke={C.psi} strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-block">
            <h3>Heat stress (WBGT) vs this worker's limit</h3>
            <ResponsiveContainer width="100%" height={150}>
              <LineChart data={smallRows} margin={{ top: 8, right: 84, bottom: 0, left: 0 }}>
                <CartesianGrid stroke={C.grid} vertical={false} />
                {axisX(now, smallXTicks)}
                <YAxis domain={wbgtDomain} stroke={C.axis} tick={AXIS_TICK} axisLine={false} tickLine={false} width={36}
                  tickFormatter={(v) => `${Number(v).toFixed(0)}°`} />
                <Tooltip labelFormatter={tooltipLabel} contentStyle={TOOLTIP_STYLE}
                  content={({ active, payload, label }) => {
                    if (!active || !payload?.length) return null
                    const r = payload[0].payload as { wbgt: number | null; wbgtRaw: number | null }
                    return (
                      <div style={{ ...TOOLTIP_STYLE, padding: '6px 10px' }}>
                        <div>{tooltipLabel(label)}</div>
                        <div>WBGT {fmt(r.wbgtRaw, 1, ' °C')} <span style={{ color: C.axis }}>(5-min mean {fmt(r.wbgt, 1)})</span></div>
                      </div>
                    )
                  }} />
                <ReferenceArea y1={worker.wbgt_limit_c} y2={wbgtDomain[1]} fill={C.limit} fillOpacity={0.07} ifOverflow="hidden" />
                <ReferenceLine y={worker.wbgt_limit_c} stroke={C.limit} strokeWidth={1.5}
                  label={{ value: `Limit ${worker.wbgt_limit_c.toFixed(1)} °C`, position: 'right', fill: C.limit, fontSize: 12 }} />
                <Line dataKey="wbgt" stroke={C.wbgt} strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <button className="btn link" onClick={() => setDetails(!details)} aria-expanded={details}>
          Details {details ? '▾' : '▸'}
        </button>
        {details && (
          <dl className="focus-details">
            <div><dt>Core temperature limit</dt><dd>{limit.toFixed(1)} °C ({p.acclimatized ? 'acclimatized' : 'unacclimatized'}, ACGIH)</dd></div>
            <div><dt>WBGT limit</dt><dd>{worker.wbgt_limit_c.toFixed(1)} °C ({p.acclimatized ? 'NIOSH REL' : 'NIOSH RAL'}, {worker.workload_observed} work)</dd></div>
            <div><dt>Workload</dt><dd>assigned {p.workload}, observed {worker.workload_observed}</dd></div>
            <div><dt>Age</dt><dd>{p.age}</dd></div>
            <div><dt>Resting heart rate</dt><dd>{fmt(p.resting_hr, 0, ' bpm')}</dd></div>
            <div><dt>Strain index</dt><dd>{fmt(worker.psi, 1)} {worker.psi_band ? `(${worker.psi_band})` : ''}</dd></div>
            <div><dt>Time since rest</dt><dd>{worker.minutes_since_rest} min</dd></div>
            <div><dt>Above heat limit since last rest</dt><dd>{worker.exposure_continuous_min} min</dd></div>
          </dl>
        )}
      </aside>
    </div>
  )
}
