import { min1 } from '../lib/format'
import { SCALE } from '../lib/scale'

export function Legend({ domain, showStaging, minN }: { domain: [number, number]; showStaging: boolean; minN: number }) {
  const mid = (domain[0] + domain[1]) / 2
  return (
    <div className="float legend" aria-label="Map legend">
      <div style={{ fontSize: 12, fontWeight: 500 }}>Median response (min)</div>
      <div className="legend-bar" style={{ background: `linear-gradient(90deg, ${SCALE.join(',')})` }} />
      <div className="legend-ticks num">
        <span>≤{min1(domain[0])}</span>
        <span>{min1(mid)}</span>
        <span>≥{min1(domain[1])}</span>
      </div>
      <div className="legend-row" title={`Fewer than ${minN} calls in the hour window`}>
        <span className="swatch-hatch" />
        Too few calls
      </div>
      {showStaging && (
        <div className="legend-row">
          <span className="swatch-dot" />
          Staging point
        </div>
      )}
    </div>
  )
}
