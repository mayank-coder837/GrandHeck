// Mirrors the JSON produced by backend/grandheck/pipeline/gateway.py and api/runner.py.

export type Level = 'NONE' | 'ADVISORY' | 'WARNING' | 'CRITICAL'

export interface Profile {
  worker_id: string
  name: string
  role: string
  age: number
  age_band: string
  acclimatized: boolean
  workload: 'light' | 'moderate' | 'heavy'
  resting_hr: number | null
}

export interface HistoryPoint {
  minute: number
  hr: number | null
  core_c: number | null
  psi: number | null
  wbgt_c: number | null
}

export interface WorkerSnapshot {
  worker_id: string
  profile: Profile
  core_limit_c: number
  wbgt_limit_c: number
  level: Level
  signal_lost: boolean
  hr: number | null
  core_c: number
  core_std_c: number
  psi: number | null
  psi_band: string | null
  skin_temp_c: number | null
  activity: number | null
  resting: boolean
  minutes_since_rest: number
  exposure_total_min: number
  exposure_continuous_min: number
  ttc_min: number | null
  ttc_expected_min: number | null
  ttc_driver: 'core' | 'psi' | null
  forecast_stale: boolean
  core_slope_c_per_h: number | null
  forecast_line: [number, number][]
  risk_line: [number, number][]
  reasons: string[]
  point: HistoryPoint
}

export interface SiteSnapshot {
  air_temp_c: number | null
  rh_pct: number | null
  solar_wm2: number | null
  wind_ms: number | null
  wbgt_c: number | null
  wbgt_method: 'liljegren' | 'liljegren_held_solar' | 'bom_shade' | null
  wbgt_trend_c_per_h: number | null
  heat_index_c: number | null
  heat_index_band: string | null
  categories: Record<string, 'low' | 'elevated' | 'high'>
  limits: Record<string, { acclimatized: number; unacclimatized: number }>
  station_stale: boolean
}

export interface Alert {
  site_id: string
  worker_id: string
  ts: string
  level: Level
  kind: 'escalated' | 'renotify' | 'resolved' | 'signal_lost' | 'signal_restored'
  ttc_min: number | null
  ttc_expected_min: number | null
  reasons: string[]
  action: string
}

export interface Tick {
  ts: string
  minute: number
  site: SiteSnapshot
  workers: WorkerSnapshot[]
  alerts: Alert[]
  truth: Record<string, { core_c: number; working: boolean }>
}

export interface RunState {
  run_id: string
  weather: string
  weather_profiles: Record<string, string>
  speed: number
  speeds: number[]
  paused: boolean
  finished: boolean
  forecaster: 'v1' | 'v2'
  profiles: Profile[]
  site: { id: string; name: string; lat: number; lon: number; utc_offset_h: number }
  thresholds: {
    core_acclimatized_c: number
    core_unacclimatized_c: number
    psi_critical: number
    ttc_advisory_min: number
    ttc_warning_min: number
    ttc_critical_min: number
    horizon_min: number
  }
}

export type ServerMessage =
  | { type: 'init'; state: RunState; ticks: Tick[]; alerts: Alert[] }
  | { type: 'tick'; tick: Tick }
  | { type: 'state'; state: RunState }
