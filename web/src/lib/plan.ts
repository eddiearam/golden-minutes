/**
 * The in-browser plan engine. Every number comes from web/public/data/plan.json and plan_zip.json, which
 * src/export_web.py builds from src/capacity.py and src/simulate.py outputs.
 *
 * A plan frees ambulances in a borough and shift: extra ambulances on duty, plus transports per hour x minutes
 * cut from hospital handover / 60 (Little's law). Each freed ambulance saves `slope` minutes per call in that
 * borough (estimated within borough x year x hour of week and borough x day; see docs/capacity.md). Staging
 * swaps in each call's response with the K = 20 staging saving. Effects add.
 */
import type { MapLayer, Sev, Stats } from './types'

export type Cls = 'lt' | 'ot'

export interface Comp {
  borough?: string
  modzcta?: string
  shift: number
  cls: Cls
  n: number
  /** response quantiles, evenly spaced probabilities from 0 to 1: today and with staging */
  q: number[]
  qs: number[]
  ch: number
  dp: number
  tr: number
  trs: number
}

interface Slope {
  s: number
  lo: number
  hi: number
}

export interface PlanData {
  boroughs: string[]
  shifts: { name: string; start: number; end: number }[]
  slope: Record<Cls, Record<string, Slope>>
  split: Record<Cls, { ch: number; dp: number; tr: number }>
  held_slope: Record<Cls, number>
  held_2025: Record<Cls, number>
  tbar: Record<string, Record<Cls, number>[]>
  transports: Record<string, number[]>
  lt_share: Record<string, number[]>
  busy: Record<string, number[]>
  max_units: number
  max_cut: number
  comps: Comp[]
  evidence: {
    pooled: Record<'resp' | 'ch' | 'dp' | 'tr' | 'held', { s: number; se: number }>
    pooled_other: number
    placebo: { own: number; other_borough: number }
    by_year: Record<string, number>
    holdout: { busy_dev: number; resp_dev: number; n: number; predicted: number }[]
    holdout_mae: number
    holdout_mae_null: number
    calls: number
  }
  workload: {
    year: number
    jobs: number
    job_mean_min: number
    to_scene: number
    on_scene: number
    transport: number
    at_hospital: number
    ambulances_busy_avg: number
    at_hospital_median_transported: number
  }[]
  rise: Record<string, { resp_mean_change: number; predicted_from_busy: number }>
  hospital: Record<string, { lt_sec_per_call: number; ambulances_freed_avg: number; ambulances_freed_weekday_15_19: number }>
  one_ambulance: { b: string; shift: number; lt_per_week: number; sec: number; min_per_week: number }[]
}

export interface Plan {
  /** extra ambulances on duty per borough, by shift [Day, Evening, Night] */
  units: Record<string, number[]>
  /** minutes cut from time at hospital per transport */
  cut: number
  staging: boolean
}

export const shiftOf = (hour: number) => (hour >= 7 && hour < 15 ? 0 : hour >= 15 && hour < 23 ? 1 : 2)

export function emptyPlan(boroughs: string[]): Plan {
  return { units: Object.fromEntries(boroughs.map((b) => [b, [0, 0, 0]])), cut: 0, staging: false }
}

export type PresetId = 'hospital' | 'ambulances' | 'staging' | 'combined'

export const PRESETS: { id: PresetId; label: string }[] = [
  { id: 'hospital', label: 'Handover' },
  { id: 'ambulances', label: '+15 ambulances' },
  { id: 'staging', label: 'Staging' },
  { id: 'combined', label: 'All three' },
]

/** Place n extra ambulance-shifts where each saves the most life-threatening minutes, at most `cap` per cell. */
export function allocate(pd: PlanData, n: number, cap = 3): Record<string, number[]> {
  const units = emptyPlan(pd.boroughs).units
  let left = n
  for (const r of [...pd.one_ambulance].sort((a, b) => b.min_per_week - a.min_per_week)) {
    if (left <= 0) break
    const k = Math.min(cap, left)
    units[r.b][r.shift] += k
    left -= k
  }
  return units
}

export function preset(pd: PlanData, id: PresetId): Plan {
  const p = emptyPlan(pd.boroughs)
  if (id === 'hospital' || id === 'combined') p.cut = 10
  if (id === 'ambulances' || id === 'combined') p.units = allocate(pd, 15)
  if (id === 'staging' || id === 'combined') p.staging = true
  return p
}

export function presetOf(pd: PlanData, plan: Plan): PresetId | null {
  for (const { id } of PRESETS) if (samePlan(preset(pd, id), plan)) return id
  return null
}

export function samePlan(a: Plan, b: Plan) {
  return a.cut === b.cut && a.staging === b.staging && JSON.stringify(a.units) === JSON.stringify(b.units)
}

export const totalUnits = (p: Plan) => Object.values(p.units).reduce((s, u) => s + u[0] + u[1] + u[2], 0)

// ---------------------------------------------------------------- pricing

/** Ambulances freed in a borough and shift for one class of call (transport rate weighted by that class). */
export function freed(pd: PlanData, plan: Plan, b: string, shift: number, cls: Cls) {
  return (plan.units[b]?.[shift] ?? 0) + (pd.tbar[b][shift][cls] * plan.cut) / 60
}

type Which = 's' | 'lo' | 'hi'

function compSave(pd: PlanData, plan: Plan, c: Comp, b: string, which: Which = 's') {
  return pd.slope[c.cls][b][which] * freed(pd, plan, b, c.shift, c.cls)
}

/** Share of a component's calls at or below y, from its evenly spaced quantiles. */
function cdf(q: number[], y: number) {
  const k = q.length - 1
  if (y < q[0]) return 0
  if (y >= q[k]) return 1
  let lo = 0
  let hi = k
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (q[mid] <= y) lo = mid
    else hi = mid
  }
  const span = q[hi] - q[lo]
  return (lo + (span > 0 ? (y - q[lo]) / span : 1)) / k
}

/** Quantile p of a mixture of components, each shifted down by its saving. */
function mixQuantile(parts: { q: number[]; n: number; save: number }[], p: number) {
  const N = parts.reduce((s, c) => s + c.n, 0)
  let lo = Math.min(...parts.map((c) => c.q[0] - c.save))
  let hi = Math.max(...parts.map((c) => c.q[c.q.length - 1]))
  for (let i = 0; i < 50; i++) {
    const mid = (lo + hi) / 2
    const f = parts.reduce((s, c) => s + c.n * cdf(c.q, mid + c.save), 0) / N
    if (f < p) lo = mid
    else hi = mid
  }
  return (lo + hi) / 2
}

const boroughOf = (c: Comp, fallback?: string) => c.borough ?? fallback ?? ''

/**
 * Stats under the plan for a set of components, anchored on exact observed stats: the plan moves the median and
 * p90 by the mixture's change, and the stage means by the call-weighted savings.
 */
export function planStats(pd: PlanData, plan: Plan, comps: Comp[], today: Stats, borough?: string): Stats {
  if (!comps.length) return today
  const N = comps.reduce((s, c) => s + c.n, 0)
  const base = comps.map((c) => ({ q: c.q, n: c.n, save: 0 }))
  const after = comps.map((c) => ({
    q: plan.staging ? c.qs : c.q,
    n: c.n,
    save: compSave(pd, plan, c, boroughOf(c, borough)),
  }))
  const dMed = mixQuantile(base, 0.5) - mixQuantile(after, 0.5)
  const dP90 = mixQuantile(base, 0.9) - mixQuantile(after, 0.9)
  let sch = 0
  let sdp = 0
  let str = 0
  for (const c of comps) {
    const save = compSave(pd, plan, c, boroughOf(c, borough))
    const sp = pd.split[c.cls]
    sch += c.n * save * sp.ch
    sdp += c.n * save * sp.dp
    str += c.n * (save * sp.tr + (plan.staging ? c.tr - c.trs : 0))
  }
  const ch = today.ch - sch / N
  const dp = today.dp - sdp / N
  const tr = today.tr - str / N
  return { n: today.n, median: today.median - dMed, p90: today.p90 - dP90, ch, dp, tr, mean: ch + dp + tr }
}

/** Mean minutes saved per call of one class, with the 95% range from the borough slopes. */
export function meanSaving(pd: PlanData, plan: Plan, comps: Comp[], cls: Cls) {
  const cs = comps.filter((c) => c.cls === cls)
  const N = cs.reduce((s, c) => s + c.n, 0)
  const stg = (c: Comp) => (plan.staging ? c.tr - c.trs : 0)
  const at = (w: Which) => cs.reduce((s, c) => s + c.n * (compSave(pd, plan, c, boroughOf(c), w) + stg(c)), 0) / N
  return { mean: at('s'), lo: at('lo'), hi: at('hi') }
}

/** Held share after the plan, using the pooled held slope per freed ambulance. */
export function heldAfter(pd: PlanData, plan: Plan, comps: Comp[], cls: Cls) {
  const cs = comps.filter((c) => c.cls === cls)
  const N = cs.reduce((s, c) => s + c.n, 0)
  const f = cs.reduce((s, c) => s + c.n * freed(pd, plan, boroughOf(c), c.shift, cls), 0) / N
  return Math.max(0, pd.held_2025[cls] - pd.held_slope[cls] * f)
}

/** Ambulances freed citywide by the handover cut, averaged over weekday 15:00-19:00. */
export function freedAtPeak(pd: PlanData, cut: number) {
  let total = 0
  let hours = 0
  for (let d = 0; d < 5; d++)
    for (let h = 15; h < 19; h++) {
      const how = d * 24 + h
      total += pd.boroughs.reduce((s, b) => s + (pd.transports[b][how] * cut) / 60, 0)
      hours++
    }
  return total / hours
}

/** Map layer under the plan: the staging or today layer minus the capacity saving at each zip and hour. */
export function planLayer(
  pd: PlanData,
  plan: Plan,
  base: MapLayer,
  zipBorough: Record<string, string>,
  sev: Sev,
): MapLayer {
  const median = base.zips.map((z, i) => {
    const b = zipBorough[z]
    const row = base.median[i]
    if (!pd.slope.lt[b]) return row
    return row.map((v, how) => {
      if (v == null) return v
      const f = (plan.units[b]?.[shiftOf(how % 24)] ?? 0) + (pd.transports[b][how] * plan.cut) / 60
      const share = sev === 'lt' ? 1 : pd.lt_share[b][how]
      const s = share * pd.slope.lt[b].s + (1 - share) * pd.slope.ot[b].s
      return Math.max(0, v - f * s)
    })
  })
  return { zips: base.zips, median, n: base.n }
}

// ---------------------------------------------------------------- URL state

export function planToQuery(pd: PlanData, plan: Plan) {
  const u = pd.boroughs.map((b) => plan.units[b].map((v) => v.toString(16)).join('')).join('')
  return { cut: String(plan.cut), u, stg: plan.staging ? '1' : '0' }
}

export function planFromQuery(pd: PlanData, q: URLSearchParams): Plan | null {
  if (!q.has('cut') && !q.has('u') && !q.has('stg')) return null
  const p = emptyPlan(pd.boroughs)
  const cut = Number(q.get('cut'))
  p.cut = Number.isFinite(cut) ? Math.max(0, Math.min(pd.max_cut, Math.round(cut))) : 0
  p.staging = q.get('stg') === '1'
  const u = q.get('u') ?? ''
  pd.boroughs.forEach((b, i) => {
    p.units[b] = [0, 1, 2].map((s) => {
      const v = parseInt(u[i * 3 + s] ?? '0', 16)
      return Number.isFinite(v) ? Math.max(0, Math.min(pd.max_units, v)) : 0
    })
  })
  return p
}

export function describe(plan: Plan) {
  const parts = []
  if (plan.cut) parts.push(`handover −${plan.cut} min`)
  const u = totalUnits(plan)
  if (u) parts.push(`+${u} ambulances`)
  if (plan.staging) parts.push('staging')
  return parts.join(' · ') || 'no changes'
}
