import { motion } from 'framer-motion'
import { useEffect, useRef } from 'react'
import { int, pct } from '../lib/format'
import type { Summary } from '../lib/types'

export function AboutSheet({ summary, onClose }: { summary: Summary; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null
    ref.current?.focus()
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      prev?.focus()
    }
  }, [onClose])
  const q = summary.quality
  return (
    <motion.div
      className="scrim"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <motion.div
        ref={ref}
        className="sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="about-title"
        tabIndex={-1}
        initial={{ x: 40, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        exit={{ x: 40, opacity: 0 }}
        transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
      >
        <button className="sheet-close" onClick={onClose}>
          Close
        </button>
        <h2 id="about-title">About the data</h2>
        <p className="caption on-white">How every number on this page was produced.</p>

        <h3>Sources</h3>
        <ul>
          <li>
            <a href="https://data.cityofnewyork.us/d/76xm-jjuj" target="_blank" rel="noreferrer">
              EMS Incident Dispatch Data
            </a>{' '}
            (FDNY, NYC Open Data): {int(q.total_rows)} incidents created 2022–2025. The app shows 2025.
          </li>
          <li>
            <a href="https://data.cityofnewyork.us/d/pri4-ifjk" target="_blank" rel="noreferrer">
              Modified Zip Code Tabulation Areas
            </a>{' '}
            (NYC DOHMH) for zip boundaries.
          </li>
          <li>
            <a href="https://data.cityofnewyork.us/d/ji82-xba5" target="_blank" rel="noreferrer">
              Facilities Database
            </a>{' '}
            (NYC Planning): {summary.stations} FDNY EMS station locations.
          </li>
          <li>
            <a href="https://open-meteo.com/en/docs/historical-weather-api" target="_blank" rel="noreferrer">
              Open-Meteo historical weather
            </a>{' '}
            for hourly Central Park weather.
          </li>
        </ul>

        <h3>Method in plain English</h3>
        <p>
          Response time runs from the moment an incident is created in the EMS dispatch system to the first unit
          arriving. It splits into call handling (until a unit is assigned), dispatch (until the unit is en route) and
          travel. Records that are standbys, transfers, never reached the scene, have impossible timestamp orders or
          stages longer than three hours are left out: {int(q.rt_ok)} incidents remain. Life-threatening means FDNY
          segments 1–3 at the time of the call.
        </p>
        <p>
          Demand is forecast one week ahead for every zip and hour with gradient boosting (time of week, holidays,
          weather and the previous weeks' calls). On 2025, which the model never saw, its hourly error was{' '}
          {summary.forecast.model.toFixed(3)} calls against {summary.forecast.baseline.toFixed(3)} for the usual
          same-hour four-week average.
        </p>
        <p>
          A travel model links each zip's travel time to its distance from the nearest EMS station, its size, the time
          of day and its borough (2025 error {summary.travel.mae_min.toFixed(2)} min per zip and time block, R²{' '}
          {summary.travel.r2.toFixed(2)}). For each four-hour block of the week, staging points are chosen among zip
          centres to minimise forecast demand × modelled travel. The optimised view subtracts the modelled travel saving
          from each real 2025 call.
        </p>

        <h3>Limitations</h3>
        <ul>
          <li>Locations are only published at zip level, so distances run between zip centres, not addresses.</li>
          <li>
            The data does not say where the responding ambulance came from. The travel model uses distance to the
            nearest station as a stand-in, and the station list is incomplete.
          </li>
          <li>
            Crew availability is not modelled: the optimised view assumes a staged ambulance is free when a call
            arrives, and that moving it does not slow other calls. The sensitivity table in the README shows results when
            it is free only half the time.
          </li>
          <li>
            {pct(q.held_share_lt, 1)} of life-threatening calls in 2025 were held waiting for a free unit. Staging
            cannot fix that delay without more units.
          </li>
          <li>
            Timestamps are entered by crews and dispatchers; some records are late, missing or out of order (see the
            data quality report).
          </li>
          <li>The hour-of-week map uses a three-hour window centred on the selected hour; cells with fewer than {summary.min_n} calls are hatched.</li>
        </ul>
      </motion.div>
    </motion.div>
  )
}
