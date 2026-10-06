import { clockFromIso, fmt } from '../format'
import type { RunState, Tick } from '../types'

const CATEGORY_TEXT = { low: 'Low', elevated: 'Elevated', high: 'High' } as const

export function TopBar({ tick, state, connected }: { tick?: Tick; state: RunState | null; connected: boolean }) {
  const site = tick?.site
  const category = site?.categories?.moderate
  const trend = site?.wbgt_trend_c_per_h
  return (
    <header className="topbar">
      <div className="brand">
        <div className="brand-name">GrandHeck</div>
        <div className="brand-sub">Heat-strain early warning · {state?.site.name ?? '…'}</div>
      </div>

      <div className="clock">
        <div className="label">Site time</div>
        <div className="big">{tick ? clockFromIso(tick.ts) : '--:--'}</div>
      </div>

      <div className={`stat wbgt cat-${category ?? 'none'}`}>
        <div className="label">
          WBGT{' '}
          {site?.wbgt_method === 'bom_shade' && (
            <span className="badge warn" title="Solar or wind data missing: shade approximation (reads low in sun)">
              shade estimate
            </span>
          )}
        </div>
        <div className="big">
          {fmt(site?.wbgt_c, 1, '°C')}
          {trend !== null && trend !== undefined && Math.abs(trend) >= 0.3 && (
            <span className="trend">{trend > 0 ? '▲' : '▼'} {Math.abs(trend).toFixed(1)}/h</span>
          )}
        </div>
        <div className="sub">
          Moderate work: <b>{category ? CATEGORY_TEXT[category] : '—'}</b>
        </div>
      </div>

      <div className="stat">
        <div className="label">Heat index</div>
        <div className="big">{fmt(site?.heat_index_c, 0, '°C')}</div>
        <div className="sub">{site?.heat_index_band ?? '—'}</div>
      </div>

      <div className="stat small">
        <div>Air {fmt(site?.air_temp_c, 1, '°C')}</div>
        <div>RH {fmt(site?.rh_pct, 0, '%')}</div>
        <div>Wind {fmt(site?.wind_ms, 1, ' m/s')}</div>
        <div>Sun {site?.solar_wm2 === null ? <span className="lost">no data</span> : fmt(site?.solar_wm2, 0, ' W/m²')}</div>
      </div>

      <div className="gateway">
        <span className={`dot ${connected ? 'ok' : 'bad'}`} />
        {connected ? 'Gateway live' : 'Reconnecting…'}
        <div className="sub">runs offline on site</div>
      </div>
    </header>
  )
}
