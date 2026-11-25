// Prices each preset plan with the app's own engine and writes docs/results/plan_presets.json.
// Usage: node --experimental-strip-types scripts/plan-presets.ts
import { readFileSync, writeFileSync } from 'node:fs'
import { PRESETS, emptyPlan, freedAtPeak, heldAfter, meanSaving, planStats, preset, type Plan, type PlanData } from '../src/lib/plan.ts'

const pd: PlanData = JSON.parse(readFileSync('public/data/plan.json', 'utf8'))
const sum = JSON.parse(readFileSync('public/data/summary.json', 'utf8'))
const lt = pd.comps.filter((c) => c.cls === 'lt')
const r = (v: number, d = 2) => Math.round(v * 10 ** d) / 10 ** d
const price = (p: Plan) => {
  const m = meanSaving(pd, p, pd.comps, 'lt')
  const o = meanSaving(pd, p, pd.comps, 'ot')
  const s = planStats(pd, p, lt, sum.city.lt.today)
  return {
    plan: p,
    lt_mean_saved_s: r(m.mean * 60, 1),
    lt_mean_saved_s_95ci: [r(m.lo * 60, 1), r(m.hi * 60, 1)],
    lt_median_before_min: sum.city.lt.today.median,
    lt_median_after_min: r(s.median, 3),
    lt_median_saved_s: r((sum.city.lt.today.median - s.median) * 60, 1),
    lt_p90_saved_s: r((sum.city.lt.today.p90 - s.p90) * 60, 1),
    other_mean_saved_s: r(o.mean * 60, 1),
    held_lt: [pd.held_2025.lt, r(heldAfter(pd, p, pd.comps, 'lt'), 4)],
    held_other: [pd.held_2025.ot, r(heldAfter(pd, p, pd.comps, 'ot'), 4)],
    ambulances_freed_weekday_15_19_by_handover: r(freedAtPeak(pd, p.cut), 1),
  }
}
const out: Record<string, unknown> = {}
for (const { id } of PRESETS) out[id] = price(preset(pd, id))
const one = { ...emptyPlan(pd.boroughs), units: Object.fromEntries(pd.boroughs.map((b) => [b, [1, 1, 1]])) }
out.one_everywhere = price(one)
for (const cut of [5, 15]) out[`handover_${cut}`] = price({ ...emptyPlan(pd.boroughs), cut })
writeFileSync('../docs/results/plan_presets.json', JSON.stringify(out, null, 1))
console.log(JSON.stringify(Object.fromEntries(Object.entries(out).map(([k, v]) => [k, { ...(v as object), plan: undefined }])), null, 1))
