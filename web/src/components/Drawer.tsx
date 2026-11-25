import { AnimatePresence, motion } from 'framer-motion'
import { useMemo } from 'react'
import type { Demand } from '../lib/types'
import { Heatmap } from './Charts'

export function Drawer({
  open,
  onToggle,
  demand,
  zip,
  mae,
}: {
  open: boolean
  onToggle: () => void
  demand: Demand | null
  zip: string | null
  mae: { model: number; baseline: number }
}) {
  const data = useMemo(() => {
    if (!demand) return null
    const actual = zip ? demand.actual[zip] : demand.city.actual
    const forecast = zip ? demand.forecast[zip] : demand.city.forecast
    if (!actual || !forecast) return null
    const err = actual.map((a, i) => forecast[i] - a)
    const max = Math.max(...actual, ...forecast)
    const emax = Math.max(...err.map(Math.abs), 1e-6)
    const meanAbs = err.reduce((s, e) => s + Math.abs(e), 0) / err.length
    return { actual, forecast, err, max, emax, meanAbs }
  }, [demand, zip])

  return (
    <section className="card drawer" aria-label="Demand heatmap">
      <button className="drawer-toggle" aria-expanded={open} onClick={onToggle}>
        <span>
          Demand by hour and weekday
          <span className="caption">
            {zip ? `ZIP ${zip}` : 'Citywide'} · life-threatening calls per hour, average 2025 week
          </span>
        </span>
        <motion.svg width="14" height="14" viewBox="0 0 14 14" animate={{ rotate: open ? 180 : 0 }} aria-hidden>
          <path d="m3 9 4-4 4 4" fill="none" stroke="#1d1d1f" strokeWidth="1.6" strokeLinecap="round" />
        </motion.svg>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
            style={{ overflow: 'hidden' }}
          >
            <div className="drawer-body">
              {data ? (
                <div className="heat-grid">
                  <Heatmap values={data.actual} max={data.max} title="Actual" caption="Observed calls per hour" />
                  <Heatmap values={data.forecast} max={data.max} title="Forecast" caption="Gradient boosting, one week ahead" />
                  <Heatmap
                    values={data.err}
                    max={data.emax}
                    diverging
                    title="Forecast error"
                    caption={`Forecast − actual · mean abs. ${data.meanAbs.toFixed(2)} calls/h`}
                  />
                </div>
              ) : (
                <div className="skel" style={{ height: 150 }} />
              )}
              <div className="caption" style={{ marginTop: 12 }}>
                Hourly 2025 holdout, every zip-hour: forecast MAE {mae.model.toFixed(3)} calls vs{' '}
                {mae.baseline.toFixed(3)} for the same-hour 4-week average. Blue = forecast too low, red = too high.
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  )
}
