import { motion } from 'framer-motion'
import { useMemo } from 'react'
import { pct, secText, titleCase } from '../lib/format'
import {
  PRESETS,
  emptyPlan,
  freedAtPeak,
  heldAfter,
  meanSaving,
  preset,
  presetOf,
  totalUnits,
  type Plan,
  type PlanData,
} from '../lib/plan'
import { Roller } from './Roller'

interface Props {
  pd: PlanData
  plan: Plan
  onChange: (p: Plan) => void
  stagingK: number
}

export function PlanCard({ pd, plan, onChange, stagingK }: Props) {
  const active = presetOf(pd, plan)
  const lt = meanSaving(pd, plan, pd.comps, 'lt')
  const ot = meanSaving(pd, plan, pd.comps, 'ot')
  const peak = useMemo(() => freedAtPeak(pd, plan.cut), [pd, plan.cut])
  const units = totalUnits(plan)
  const shortName = (b: string) => titleCase(b)

  const setUnit = (b: string, s: number, v: number) => {
    const u = { ...plan.units, [b]: [...plan.units[b]] }
    u[b][s] = Math.max(0, Math.min(pd.max_units, v))
    onChange({ ...plan, units: u })
  }

  return (
    <section className="card panel-card plan-card" aria-labelledby="plan-title">
      <div className="panel-head">
        <div>
          <h2 id="plan-title" className="section-title">
            Your plan
          </h2>
          <div className="caption">Priced on every 2025 call. Try a preset or set each lever.</div>
        </div>
        <button className="clear-btn" onClick={() => onChange(emptyPlan(pd.boroughs))}>
          Reset
        </button>
      </div>

      <div className="inner plan-result" aria-live="polite">
        <Row
          k="Life-threatening calls"
          v={lt.mean}
          note={
            lt.hi - lt.lo > 1 / 120 ? `average · 95% CI ${secText(lt.lo).replace(/\u00a0s$/, '')}–${secText(lt.hi)}` : 'average'
          }
        />
        <Row k="Other calls" v={ot.mean} note="average" />
        <Held k="Held, life-threatening" from={pd.held_2025.lt} to={heldAfter(pd, plan, pd.comps, 'lt')} />
        <Held k="Held, other calls" from={pd.held_2025.ot} to={heldAfter(pd, plan, pd.comps, 'ot')} />
      </div>

      <div className="chips" role="group" aria-label="Example plans">
        {PRESETS.map((p) => (
          <button
            key={p.id}
            className="chip"
            aria-pressed={active === p.id}
            onClick={() => onChange(preset(pd, p.id))}
          >
            {p.label}
          </button>
        ))}
      </div>

      <div className="lever">
        <div className="lever-head">
          <label htmlFor="cut">Faster hospital handover</label>
          <span className="num lever-val">{plan.cut ? `−${plan.cut} min` : 'None'}</span>
        </div>
        <input
          id="cut"
          className="range"
          type="range"
          min={0}
          max={pd.max_cut}
          step={1}
          value={plan.cut}
          onChange={(e) => onChange({ ...plan, cut: Number(e.target.value) })}
          aria-valuetext={`${plan.cut} minutes less at hospital per transport`}
        />
        <div className="caption lever-note">
          {plan.cut
            ? `Frees about ${Math.round(peak)} ambulances at the weekday 15:00–19:00 peak.`
            : 'Minutes cut from time at hospital per transport (median 41 min).'}
        </div>
      </div>

      <div className="lever">
        <div className="lever-head">
          <span id="units-label">Extra ambulances on duty</span>
          <span className="num lever-val">{units ? `+${units} per day` : 'None'}</span>
        </div>
        <table className="unit-grid" aria-labelledby="units-label">
          <thead>
            <tr>
              <th />
              {pd.shifts.map((s) => (
                <th key={s.name} scope="col">
                  {s.name}
                  <small className="num">
                    {String(s.start).padStart(2, '0')}–{String(s.end).padStart(2, '0')}
                  </small>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pd.boroughs.map((b) => (
              <tr key={b}>
                <th scope="row">{shortName(b)}</th>
                {[0, 1, 2].map((s) => (
                  <td key={s}>
                    <Stepper
                      value={plan.units[b][s]}
                      max={pd.max_units}
                      label={`${shortName(b)} ${pd.shifts[s].name.toLowerCase()} shift`}
                      onChange={(v) => setUnit(b, s, v)}
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        <div className="caption lever-note">
          One more staffed ambulance on that shift, every day (up to {pd.max_units}).
        </div>
      </div>

      <div className="lever lever-switch">
        <button
          className="switch"
          role="switch"
          aria-checked={plan.staging}
          aria-labelledby="stg-label"
          onClick={() => onChange({ ...plan, staging: !plan.staging })}
        >
          <motion.span className="switch-knob" layout transition={{ type: 'spring', stiffness: 600, damping: 38 }} />
        </button>
        <div>
          <div id="stg-label">Stage idle ambulances at {stagingK} points</div>
          <div className="caption">Assumes the staged ambulance is free.</div>
        </div>
      </div>

    </section>
  )
}

function Row({ k, v, note }: { k: string; v: number; note: string }) {
  const zero = Math.round(v * 60) <= 0
  return (
    <div className="pr-row">
      <span className="pr-k">{k}</span>
      <span className={`pr-v num ${zero ? 'muted' : ''}`}>
        {zero ? 'No change' : <>−<Roller value={secText(v)} /></>}
      </span>
      <span className="pr-note">{zero ? '' : note}</span>
    </div>
  )
}

function Held({ k, from, to }: { k: string; from: number; to: number }) {
  const same = Math.abs(from - to) < 0.0005
  return (
    <div className="pr-row">
      <span className="pr-k">{k}</span>
      <span className="pr-v num small">
        {pct(from, 1)}
        {!same && (
          <>
            {' → '}
            <b>{pct(to, 1)}</b>
          </>
        )}
      </span>
      <span className="pr-note">{same ? 'of calls, 2025' : 'of calls'}</span>
    </div>
  )
}

function Stepper({ value, max, label, onChange }: { value: number; max: number; label: string; onChange: (v: number) => void }) {
  return (
    <div className={`stepper ${value ? 'on' : ''}`} role="group" aria-label={label}>
      <button aria-label={`One fewer, ${label}`} disabled={value <= 0} onClick={() => onChange(value - 1)}>
        −
      </button>
      <span className="num" aria-live="polite">
        {value}
      </span>
      <button aria-label={`One more, ${label}`} disabled={value >= max} onClick={() => onChange(value + 1)}>
        +
      </button>
    </div>
  )
}
