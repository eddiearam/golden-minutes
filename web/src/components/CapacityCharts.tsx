import * as d3 from 'd3'
import { motion, useReducedMotion } from 'framer-motion'
import { useMemo } from 'react'
import { int, secText } from '../lib/format'
import { describe, emptyPlan, meanSaving, samePlan, type Plan, type PlanData } from '../lib/plan'

const ease = [0.22, 1, 0.36, 1] as const

/** Average life-threatening seconds saved by each lever alone, and by the current plan. */
export function LeversChart({ pd, plan, stagingK }: { pd: PlanData; plan: Plan; stagingK: number }) {
  const reduce = useReducedMotion()
  const rows = useMemo(() => {
    const e = emptyPlan(pd.boroughs)
    const one = { ...e, units: Object.fromEntries(pd.boroughs.map((b) => [b, [1, 1, 1]])) }
    const list: { label: string; sub: string; p: Plan }[] = [
      { label: `Stage idle ambulances`, sub: `${stagingK} points, if free`, p: { ...e, staging: true } },
      { label: '+1 ambulance everywhere', sub: '15 more per day', p: one },
      { label: 'Handover −5 min', sub: 'per transport', p: { ...e, cut: 5 } },
      { label: 'Handover −10 min', sub: '', p: { ...e, cut: 10 } },
      { label: 'Handover −15 min', sub: '', p: { ...e, cut: 15 } },
    ]
    const out = list.map((r) => ({ ...r, v: meanSaving(pd, r.p, pd.comps, 'lt').mean, mine: false }))
    const isEmpty = samePlan(plan, e)
    if (!isEmpty && !list.some((r) => samePlan(r.p, plan)))
      out.push({
        label: 'Your plan',
        sub: describe(plan),
        p: plan,
        v: meanSaving(pd, plan, pd.comps, 'lt').mean,
        mine: true,
      })
    return out.map((r) => ({ ...r, mine: r.mine || (!isEmpty && samePlan(r.p, plan)) }))
  }, [pd, plan, stagingK])
  const max = Math.max(...rows.map((r) => r.v), 1 / 60)
  return (
    <div className="lever-bars" role="list">
      {rows.map((r) => (
        <div key={r.label} className={`lb-row ${r.mine ? 'mine' : ''}`} role="listitem">
          <div className="lb-text">
            <span className="lb-label">{r.label}</span>
            {r.sub && <span className="lb-sub">{r.sub}</span>}
          </div>
          <div className="lb-bar">
            <motion.i
              initial={false}
              animate={{ width: `${(100 * r.v) / max}%` }}
              transition={{ duration: reduce ? 0 : 0.35, ease }}
            />
          </div>
          <span className="lb-val num">−{secText(r.v)}</span>
        </div>
      ))}
    </div>
  )
}

const STAGES = [
  { key: 'to_scene' as const, label: 'Getting to the scene' },
  { key: 'on_scene' as const, label: 'On scene' },
  { key: 'transport' as const, label: 'Transport to hospital' },
  { key: 'at_hospital' as const, label: 'At hospital' },
]

/** Change in average minutes per job, first year to last, by stage. */
export function WhySlower({ pd }: { pd: PlanData }) {
  const reduce = useReducedMotion()
  const a = pd.workload[0]
  const b = pd.workload[pd.workload.length - 1]
  const rows = STAGES.map((s) => ({ ...s, d: b[s.key] - a[s.key], v: b[s.key] }))
  const max = Math.max(...rows.map((r) => Math.abs(r.d)))
  return (
    <div>
      <div className="why-head num">
        <div>
          <div className="why-big">
            {a.job_mean_min.toFixed(1)} → {b.job_mean_min.toFixed(1)}
            <small> min</small>
          </div>
          <div className="caption on-white">average job, {a.year} → {b.year}</div>
        </div>
        <div>
          <div className="why-big">
            {Math.round(a.ambulances_busy_avg)} → {Math.round(b.ambulances_busy_avg)}
          </div>
          <div className="caption on-white">ambulances busy at any moment, on average</div>
        </div>
      </div>
      <div className="label" style={{ marginTop: 16 }}>
        Extra minutes per job, {a.year} → {b.year}
      </div>
      {rows.map((r) => (
        <div key={r.key} className="why-row">
          <span className="why-k">{r.label}</span>
          <div className="lb-bar red">
            <motion.i
              initial={false}
              animate={{ width: `${(100 * Math.max(r.d, 0)) / max}%` }}
              transition={{ duration: reduce ? 0 : 0.35, ease }}
            />
          </div>
          <span className="why-v num">
            {r.d >= 0 ? '+' : '−'}
            {Math.abs(r.d).toFixed(1)}
          </span>
        </div>
      ))}
      <p className="caption on-white" style={{ marginTop: 12 }}>
        Jobs barely changed ({int(a.jobs / 1000)}k in {a.year}, {int(b.jobs / 1000)}k in {b.year}), but each one took{' '}
        {(b.job_mean_min - a.job_mean_min).toFixed(1)} min longer. Getting to the scene grew most, and slower arrivals
        keep ambulances busy longer: a loop. Time at hospital is the largest single stage of a transport (median{' '}
        {b.at_hospital_median_transported.toFixed(0)} min).
      </p>
    </div>
  )
}

/** Holdout check: 2025 binned change in life-threatening response vs busy ambulances, with the 2022-2024 fit. */
export function Evidence({ pd }: { pd: PlanData }) {
  const e = pd.evidence
  const pts = e.holdout.filter((r) => Math.abs(r.busy_dev) <= 20)
  const W = 340
  const H = 170
  const m = { t: 10, r: 10, b: 34, l: 52 }
  const x = d3.scaleLinear([-18, 18], [m.l, W - m.r])
  const ext = d3.max(pts, (r) => Math.max(Math.abs(r.resp_dev), Math.abs(r.predicted))) ?? 1
  const y = d3.scaleLinear([-ext * 1.15, ext * 1.15], [H - m.b, m.t]).nice()
  const line = d3
    .line<(typeof pts)[number]>()
    .x((r) => x(r.busy_dev))
    .y((r) => y(r.predicted))
  const sec = e.pooled.resp.s * 60
  const ci = 1.96 * e.pooled.resp.se * 60
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img"
        aria-label={`Each extra busy ambulance adds ${sec.toFixed(1)} seconds to life-threatening response`}>
        <g className="axis">
          {y.ticks(4).map((t) => (
            <g key={t} transform={`translate(0,${y(t)})`}>
              <line x1={m.l} x2={W - m.r} stroke={t === 0 ? '#c7c7cc' : undefined} />
              <text x={m.l - 6} dy="0.32em" textAnchor="end">
                {t === 0 ? '0' : `${t > 0 ? '+' : '−'}${Math.abs(t).toFixed(1)}`}
              </text>
            </g>
          ))}
          {[-15, -10, -5, 0, 5, 10, 15].map((t) => (
            <text key={t} x={x(t)} y={H - m.b + 15} textAnchor="middle">
              {t > 0 ? `+${t}` : t < 0 ? `−${-t}` : '0'}
            </text>
          ))}
          <text x={(m.l + W - m.r) / 2} y={H - 2} textAnchor="middle">
            Busy ambulances vs usual for that borough and hour
          </text>
          <text transform={`translate(10,${(m.t + H - m.b) / 2}) rotate(-90)`} textAnchor="middle">
            Response change (min)
          </text>
        </g>
        <path d={line(pts) ?? ''} fill="none" stroke="var(--red)" strokeWidth={2} />
        {pts.map((r) => (
          <circle key={r.busy_dev} cx={x(r.busy_dev)} cy={y(r.resp_dev)} r={4} fill="#1d1d1f" />
        ))}
      </svg>
      <div className="caption on-white" style={{ display: 'flex', gap: 14, marginTop: 4 }}>
        <span>
          <i className="key-dot" /> Observed 2025
        </span>
        <span>
          <i className="key-line" /> Predicted from 2022–2024
        </span>
      </div>
      <p className="caption on-white" style={{ marginTop: 10 }}>
        Each extra busy ambulance adds {sec.toFixed(1)} s to a life-threatening response (95% CI {(sec - ci).toFixed(1)}–
        {(sec + ci).toFixed(1)} s, {int(e.calls)} calls), mostly through longer travel, and {(e.pooled_other * 60).toFixed(0)} s
        to other calls. Calls are compared only with others in the same borough, hour of week and day, so staffing
        patterns, weather and traffic cancel out. Busy ambulances in a different borough have no effect (
        {(e.placebo.other_borough * 60).toFixed(1)} s). Error on 2025: {e.holdout_mae.toFixed(2)} min, against{' '}
        {e.holdout_mae_null.toFixed(2)} assuming no effect. Beyond 20 more or fewer busy than usual (under 0.2% of
        calls) the effect flattens, so the plan is capped.
      </p>
    </div>
  )
}
