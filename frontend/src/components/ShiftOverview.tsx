import { useMemo } from 'react'
import {
  CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis,
} from 'recharts'
import { axisTick, domainWithPadding, makeClock, rollingMean } from '../chartUtils'
import { LEVEL_LABEL } from '../format'
import { tooltipStyle, useTheme } from '../theme'
import type { Alert, Tick } from '../types'

const SMOOTH_MIN = 5

interface Marker { minute: number; y: number; level: 'WARNING' | 'CRITICAL'; who: string; clock: string }

/** One-glance story of the shift: site heat over time, and when warnings fired. */
export function ShiftOverview({ ticks, alerts, names }: {
  ticks: Tick[]
  alerts: Alert[]
  names: Record<string, string>
}) {
  const { t } = useTheme()
  const last = ticks[ticks.length - 1]

  const rows = useMemo(() => {
    const smooth = rollingMean(ticks.map((tk) => tk.site.wbgt_c), SMOOTH_MIN)
    return ticks.map((tk, i) => ({ minute: tk.minute, wbgt: smooth[i] }))
  }, [ticks])

  const header = (
    <div className="panel-head">
      <div className="section-head">
        <span className="eyebrow">Shift overview</span>
        <h2>Site heat and alerts</h2>
      </div>
      <div className="legend">
        <span><i className="sw line" style={{ background: t.advisory }} />Site WBGT (5-min mean)</span>
        <span><i className="sw line" style={{ background: t.red }} />Heavy-work limit</span>
        <span><i className="sw dash" style={{ borderColor: t.muted }} />Moderate-work limit</span>
        <span><i className="dot" style={{ background: t.warning }} />Warning</span>
        <span><i className="dot" style={{ background: t.critical }} />Critical</span>
        <span className="muted">Limits: NIOSH REL, acclimatized</span>
      </div>
    </div>
  )
  if (!last || rows.length < 2) return <section className="overview panel">{header}</section>

  const clock = makeClock(last)
  const heavy = last.site.limits.heavy?.acclimatized
  const moderate = last.site.limits.moderate?.acclimatized
  const values = rows.map((r) => r.wbgt).filter((v): v is number => v != null)
  const domain = domainWithPadding([...values, ...[heavy, moderate].filter((v): v is number => v != null)], 1, 1)

  // Alert markers along the bottom of the plot, at the minute each Warning/Critical fired.
  const minuteOf = new Map(ticks.map((tk) => [tk.ts, tk.minute]))
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
      {header}
      <div className="chart-area">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: 136, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={t.grid} vertical={false} />
            <XAxis dataKey="minute" type="number" domain={[start, now]} ticks={clock.halfHours(start, now)}
              tickFormatter={clock.label} tick={axisTick(t)} axisLine={false} tickLine={false} />
            <YAxis domain={domain} tick={axisTick(t)} axisLine={false} tickLine={false} width={36}
              tickFormatter={(v) => `${Number(v).toFixed(0)}°`} />
            <Tooltip contentStyle={tooltipStyle(t)} labelStyle={{ color: t.muted }} itemStyle={{ color: t.text }}
              cursor={{ stroke: t.border }} labelFormatter={(m) => clock.label(Number(m))}
              formatter={(v, name) => (name === 'wbgt' ? [`${Number(v).toFixed(1)} °C`, 'WBGT (5-min mean)'] : [v as string, name as string])} />
            {heavy != null && (
              <ReferenceLine y={heavy} stroke={t.red} strokeWidth={1.5}
                label={{ value: `Heavy work ${heavy.toFixed(1)} °C`, position: 'right', fill: t['red-text'], fontSize: 12 }} />
            )}
            {moderate != null && (
              <ReferenceLine y={moderate} stroke={t.muted} strokeWidth={1.5} strokeDasharray="5 4"
                label={{ value: `Moderate work ${moderate.toFixed(1)} °C`, position: 'right', fill: t.muted, fontSize: 12 }} />
            )}
            <Line dataKey="wbgt" name="wbgt" stroke={t.advisory} strokeWidth={2} dot={false} isAnimationActive={false} />
            {markers.length > 0 && (   // an empty Scatter falls back to the chart's rows
            <Scatter data={markers} dataKey="y" isAnimationActive={false} tooltipType="none"
              shape={(props: { cx?: number; cy?: number; payload?: Marker }) => {
                const m = props.payload!
                return (
                  <circle cx={props.cx} cy={props.cy} r={4.5} fill={m.level === 'CRITICAL' ? t.critical : t.warning}
                    stroke={t['surface-sunk']} strokeWidth={1.5}>
                    <title>{`${m.clock} · ${m.who} · ${LEVEL_LABEL[m.level]}`}</title>
                  </circle>
                )
              }} />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}
