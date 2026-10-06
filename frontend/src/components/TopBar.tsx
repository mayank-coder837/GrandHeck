import { clockFromIso, fmt } from '../format'
import type { ThemeName } from '../theme'
import type { RunState, Tick } from '../types'
import { RedlineMark } from './RedlineMark'

const CATEGORY_TEXT = { low: 'Low', elevated: 'Elevated', high: 'High' } as const
const TREND_MIN_HISTORY_MIN = 15
const TREND_MIN_ABS_C_PER_H = 0.3

export function TopBar({ tick, state, connected, historyMinutes, theme, onToggleTheme }: {
  tick?: Tick
  state: RunState | null
  connected: boolean
  historyMinutes: number
  theme: ThemeName
  onToggleTheme: () => void
}) {
  const site = tick?.site
  const category = site?.categories?.moderate
  const trend = historyMinutes >= TREND_MIN_HISTORY_MIN ? site?.wbgt_trend_c_per_h ?? null : null
  const showTrend = trend !== null && Math.abs(trend) >= TREND_MIN_ABS_C_PER_H

  const quality =
    site?.wbgt_method === 'bom_shade'
      ? 'Solar or wind data missing: using a shade-only WBGT estimate, which reads low in full sun.'
      : site?.wbgt_method === 'liljegren_held_solar'
        ? 'Solar sensor offline: holding its last good reading.'
        : site?.station_stale
          ? 'Weather station data is stale.'
          : null

  const wbgtTip = [
    'WBGT estimated from weather data (Liljegren et al. 2008).',
    site?.heat_index_c != null ? `Heat index (for comparison): ${site.heat_index_c.toFixed(0)} °C, ${site.heat_index_band}.` : '',
    quality ?? '',
  ].filter(Boolean).join('\n')

  const statusTip = connected
    ? `Gateway live · runs offline on site · forecaster ${state?.forecaster ?? '…'}`
    : 'Reconnecting to the gateway…'

  return (
    <header className="topbar">
      <div className="brand">
        <RedlineMark />
        <div style={{ minWidth: 0 }}>
          <div className="wordmark">Redline</div>
          <div className="tagline">Heat-strain early warning · {state?.site.name ?? '…'}</div>
        </div>
      </div>

      <div className="top-right">
        <div className="clock" title="Site time">{tick ? clockFromIso(tick.ts) : '--:--'}</div>

        <div className={`wbgt-tile cat-${category ?? 'none'}`} title={wbgtTip}>
          <div className="wbgt-main">
            <span className="wbgt-label">WBGT</span>
            <span className="wbgt-value">{fmt(site?.wbgt_c, 1)}<span className="unit">°C</span></span>
            {showTrend && (
              <span className={`trend ${trend! > 0 ? 'up' : 'down'}`}>
                {trend! > 0 ? '▲' : '▼'} {Math.abs(trend!).toFixed(1)}/h
              </span>
            )}
            {category && <span className={`cat-label cat-${category}`}>{CATEGORY_TEXT[category]} for moderate work</span>}
            {quality && <span className="quality" title={quality} aria-label={quality}>⚠</span>}
          </div>
          <div className="small">
            Air {fmt(site?.air_temp_c, 1, ' °C')} · RH {fmt(site?.rh_pct, 0, '%')} · Wind {fmt(site?.wind_ms, 1, ' m/s')} ·
            Sun {site?.solar_wm2 == null ? 'no data' : `${site.solar_wm2.toFixed(0)} W/m²`}
          </div>
        </div>

        <span className={`live-dot ${connected ? 'ok' : 'bad'}`} title={statusTip} aria-label={statusTip} />
        <button className="theme-toggle" onClick={onToggleTheme} title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme (T)`}
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}>
          {theme === 'dark' ? (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <circle cx="12" cy="12" r="4" />
              <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
            </svg>
          )}
        </button>
      </div>
    </header>
  )
}
