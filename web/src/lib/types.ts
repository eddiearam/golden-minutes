export type View = 'today' | 'opt'
export type Sev = 'lt' | 'all'

export interface Stats {
  n: number
  median: number
  p90: number
  /** mean minutes per stage; they add up to the mean response */
  ch: number
  dp: number
  tr: number
  mean: number
}

export interface ZipDetail {
  borough: string
  lt: { today: Stats; opt: Stats } | null
  all: { today: Stats; opt: Stats } | null
}

export interface BoroughRow {
  name: string
  lt: { today: Stats; opt: Stats }
  all: { today: Stats; opt: Stats }
}

export interface KRow {
  k: number
  median_saved: number
  p90_saved: number
  mean_saving_per_call: number
  share_calls_improved: number
  opt_median: number
  opt_p90: number
}

export interface SensRow {
  k: number
  factor: string
  value: string
  median_saved: number
  p90_saved: number
  mean_saving_per_call: number
}

export interface Summary {
  year: number
  k_default: number
  city: { lt: { today: Stats; opt: Stats }; all: { today: Stats; opt: Stats } }
  boroughs: BoroughRow[]
  k_results: KRow[]
  sensitivity: SensRow[]
  findings: { id: string; title: string; text: string }[]
  forecast: { model: number; baseline: number; improvement_pct: number; block_model: number; block_baseline: number }
  travel: { mae_min: number; r2: number; test_cells: number }
  quality: { total_rows: number; rt_ok: number; held_share_lt: number }
  scale: { lt: [number, number]; all: [number, number] }
  min_n: number
  stations: number
  hospitals: number
  generated: string
}

export interface MapLayer {
  zips: string[]
  /** [zip][hour of week] median minutes, null when fewer than min_n calls */
  median: (number | null)[][]
  n: number[][]
}

export interface Demand {
  zips: string[]
  /** mean calls per week at each hour of week, 2025 */
  actual: Record<string, number[]>
  forecast: Record<string, number[]>
  city: { actual: number[]; forecast: number[]; baseline: number[] }
}

/** k -> block (0..41) -> [lon, lat, zip][] */
export type Staging = Record<string, Record<string, [number, number, string][]>>
