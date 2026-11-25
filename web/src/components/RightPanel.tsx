import { AnimatePresence, motion } from 'framer-motion'
import { int, min1, pct, savedChip, savedText, titleCase } from '../lib/format'
import type { Demand, Sev, Summary, View, ZipDetail } from '../lib/types'
import { Breakdown, DemandLine, Fairness } from './Charts'
import { ZipSearch } from './ZipSearch'

interface Props {
  summary: Summary
  details: Record<string, ZipDetail>
  demand: Demand | null
  view: View
  sev: Sev
  how: number
  selected: string | null
  onSelect: (z: string | null) => void
}

const SEV_LABEL = { lt: 'life-threatening calls', all: 'all calls' }

export function RightPanel({ summary, details, demand, view, sev, how, selected, onSelect }: Props) {
  const zipList = Object.entries(details).map(([id, d]) => ({ id, borough: d.borough }))
  const z = selected ? details[selected] : null
  const zs = z ? z[sev] : null
  const city = summary.city[sev]
  const s = zs ?? city
  const cur = view === 'opt' ? s.opt : s.today
  const showOpt = view === 'opt'

  return (
    <aside className="panel" aria-label="Details">
      <div className="card panel-card">
        <ZipSearch zips={zipList} onSelect={onSelect} />
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={selected ?? 'city'}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="panel-head" style={{ marginTop: 20 }}>
              <div>
                <h2 className="section-title">{selected ? `ZIP ${selected}` : 'New York City'}</h2>
                <div className="caption">
                  {selected && z ? `${titleCase(z.borough)} · ` : ''}
                  {sev === 'lt' ? 'Life-threatening' : 'All calls'} · 2025 · {int(s.today.n)} calls
                </div>
              </div>
              {selected && (
                <button className="clear-btn" onClick={() => onSelect(null)}>
                  Citywide
                </button>
              )}
            </div>
            {zs === null && selected ? (
              <p className="caption" style={{ marginTop: 16 }}>
                Too few {SEV_LABEL[sev]} in this zip in 2025 to report response times reliably.
              </p>
            ) : (
              <>
                <div className="stat-row">
                  <Stat k="Median response" v={cur.median} today={s.today.median} opt={showOpt} />
                  <Stat k="90th percentile" v={cur.p90} today={s.today.p90} opt={showOpt} />
                </div>
                <div className="inner chart-box">
                  <div className="label">Where the minutes go</div>
                  <Breakdown today={s.today} opt={s.opt} showOpt={showOpt} />
                  <div className="caption">
                    Average minutes per stage. Call handling: incident created to unit assigned. Dispatch: assigned to
                    en route. Travel: en route to on scene.
                  </div>
                </div>
              </>
            )}
            {demand && (
              <div className="inner chart-box">
                <div className="label" style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>Life-threatening demand across the week</span>
                </div>
                <DemandLine
                  actual={selected ? (demand.actual[selected] ?? demand.city.actual) : demand.city.actual}
                  forecast={selected ? (demand.forecast[selected] ?? demand.city.forecast) : demand.city.forecast}
                  how={how}
                />
                <div className="caption" style={{ display: 'flex', gap: 14, marginTop: 4 }}>
                  <span>
                    <Key color="#1d1d1f" /> Actual 2025
                  </span>
                  <span>
                    <Key color="var(--seg-dispatch)" /> Forecast
                  </span>
                  <span style={{ marginLeft: 'auto' }}>Calls per hour, average week</span>
                </div>
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </div>

      <div className="card panel-card">
        <h3 className="section-title" style={{ fontSize: 17 }}>
          Borough fairness
        </h3>
        <div className="caption">Median response, {SEV_LABEL[sev]}, 2025</div>
        <div className="inner chart-box">
          <Fairness rows={summary.boroughs} sev={sev} highlight={z?.borough} />
          <div className="caption" style={{ display: 'flex', gap: 14, marginTop: 6 }}>
            <span>
              <Key color="#8e8e93" /> Today
            </span>
            <span>
              <Key color="var(--green)" /> Optimised staging ({summary.k_default} points)
            </span>
          </div>
        </div>
      </div>

      {!selected && (
        <div className="card panel-card">
          <h3 className="section-title" style={{ fontSize: 17 }}>
            Staging scenarios
          </h3>
          <div className="caption">Life-threatening calls, 2025, staged unit assumed free</div>
          <div className="inner chart-box">
            <table className="k-table num">
              <thead>
                <tr>
                  <th>Staging points</th>
                  <th>Median saved</th>
                  <th>p90 saved</th>
                  <th>Calls helped</th>
                </tr>
              </thead>
              <tbody>
                {summary.k_results.map((r) => (
                  <tr key={r.k} className={r.k === summary.k_default ? 'active' : ''}>
                    <td>{r.k}</td>
                    <td>{savedText(r.median_saved)}</td>
                    <td>{savedText(r.p90_saved)}</td>
                    <td>{pct(r.share_calls_improved)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {!selected && (
        <div className="card panel-card">
          <h3 className="section-title" style={{ fontSize: 17 }}>
            What the data shows
          </h3>
          <div className="inner chart-box">
            {summary.findings.map((f) => (
              <p key={f.id} className="finding">
                <b>{f.title}.</b> {f.text}
              </p>
            ))}
          </div>
        </div>
      )}
    </aside>
  )
}

function Stat({ k, v, today, opt }: { k: string; v: number; today: number; opt: boolean }) {
  const d = today - v
  return (
    <div className="inner stat">
      <div className="k">{k}</div>
      <div className="v num">
        {min1(v)}
        <small>min</small>
      </div>
      {opt ? (
        <div className="delta num">{savedChip(d) === 'No change' ? 'No change vs today' : `${savedChip(d)} vs today`}</div>
      ) : (
        <div className="delta muted">Observed 2025</div>
      )}
    </div>
  )
}

function Key({ color }: { color: string }) {
  return (
    <i
      style={{
        display: 'inline-block',
        width: 10,
        height: 3,
        borderRadius: 2,
        background: color,
        verticalAlign: 'middle',
        marginRight: 5,
      }}
    />
  )
}
