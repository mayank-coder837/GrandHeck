import { useMemo } from 'react'
import {
  CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis,
} from 'recharts'
import { AXIS_TICK, CHART, TOOLTIP_STYLE, domainWithPadding, makeClock, rollingMean } from '../chartUtils'
import { LEVEL_LABEL } from '../format'
import type { Alert, Tick } from '../types'

const SMOOTH_MIN = 5

interface Marker { minute: number; y: number; level: 'WARNING' | 'CRITICAL'; who: string; clock: string }

/** One-glance story of the shift: site heat over time, and when warnings fired. */
export function ShiftOverview({ ticks, alerts, names }: {
  ticks: Tick[]
  alerts: Alert[]
  names: Record<string, string>
}) {
  const last = ticks[ticks.length - 1]

  const rows = useMemo(() => {
    const smooth = rollingMean(ticks.map((t) => t.site.wbgt_c), SMOOTH_MIN)
    return ticks.map((t, i) => ({ minute: t.minute, wbgt: smooth[i], raw: t.site.wbgt_c }))
  }, [ticks])

  if (!last || rows.length < 2) return <section className="overview panel"><h2>Shift overview</h2></section>

  const clock = makeClock(last)
  const limits = last.site.limits
  const heavy = limits.heavy?.acclimatized
  const moderate = limits.moderate?.acclimatized
  const values = rows.map((r) => r.wbgt).filter((v): v is number => v != null)
  const domain = domainWithPadding([...values, ...[heavy, moderate].filter((v): v is number => v != null)], 1, 1)

  // Alert markers along the bottom of the plot, at the minute each Warning/Critical fired.
  const minuteOf = new Map(ticks.map((t) => [t.ts, t.minute]))
  const markers: Marker[] = alerts
    .filter((a) => a.kind === 'escalated' && (a.level === 'WARNING' || a.level === 'CRITICAL') && minuteOf.has(a.ts))
    .map((a) => ({
      minute: minuteOf.get(a.ts)!, y: domain[0] + 0.35, level: a.level as Marker['level'],
      who: names[a.worker_id] ?? a.worker_id, clock: a.ts.slice(11, 16),
    }))

  const start = rows[0].minute
  const now = last.minute

  return (
    <section className="overview panel" aria-label="Shift overview">
      <div className="panel-head">
        <h2>Shift overview</h2>
        <div className="legend">
          <span><i className="sw line" style={{ background: CHART.wbgt }} />Site WBGT (5-min mean)</span>
          <span className="muted">Limits: NIOSH REL, acclimatized</span>
          <span><i className="dot" style={{ background: CHART.warning }} />Warning fired</span>
          <span><i className="dot" style={{ background: CHART.critical }} />Critical fired</span>
        </div>
      </div>
      <div className="overview-chart">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: 136, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={CHART.grid} vertical={false} />
            <XAxis dataKey="minute" type="number" domain={[start, now]} ticks={clock.halfHours(start, now)}
              tickFormatter={clock.label} stroke={CHART.axis} tick={AXIS_TICK} axisLine={false} tickLine={false} />
            <YAxis domain={domain} stroke={CHART.axis} tick={AXIS_TICK} axisLine={false} tickLine={false} width={36}
              tickFormatter={(v) => `${Number(v).toFixed(0)}°`} />
            <Tooltip contentStyle={TOOLTIP_STYLE} labelFormatter={(m) => clock.label(Number(m))}
              formatter={(v, name) => (name === 'wbgt' ? [`${Number(v).toFixed(1)} °C`, 'WBGT (5-min mean)'] : [v as string, name as string])}
              filterNull />
            {heavy != null && (
              <ReferenceLine y={heavy} stroke={CHART.limit} strokeWidth={1.5}
                label={{ value: `Heavy work ${heavy.toFixed(1)} °C`, position: 'right', fill: CHART.limit, fontSize: 12 }} />
            )}
            {moderate != null && (
              <ReferenceLine y={moderate} stroke={CHART.warning} strokeWidth={1.5} strokeDasharray="5 4"
                label={{ value: `Moderate work ${moderate.toFixed(1)} °C`, position: 'right', fill: CHART.warning, fontSize: 12 }} />
            )}
            <Line dataKey="wbgt" name="wbgt" stroke={CHART.wbgt} strokeWidth={2} dot={false} isAnimationActive={false} />
            <Scatter data={markers} dataKey="y" isAnimationActive={false} tooltipType="none"
              shape={(props: { cx?: number; cy?: number; payload?: Marker }) => {
                const m = props.payload!
                return (
                  <circle cx={props.cx} cy={props.cy} r={5} fill={m.level === 'CRITICAL' ? CHART.critical : CHART.warning}
                    stroke="#0a0f1d" strokeWidth={1.5}>
                    <title>{`${m.clock} · ${m.who} · ${LEVEL_LABEL[m.level]}`}</title>
                  </circle>
                )
              }} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}
