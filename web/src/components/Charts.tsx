import * as d3 from 'd3'
import { motion, useReducedMotion } from 'framer-motion'
import { DAYS, min1, titleCase } from '../lib/format'
import type { BoroughRow, Sev, Stats } from '../lib/types'

const SEG = [
  { key: 'ch' as const, label: 'Call handling', color: 'var(--seg-call)' },
  { key: 'dp' as const, label: 'Dispatch', color: 'var(--seg-dispatch)' },
  { key: 'tr' as const, label: 'Travel', color: 'var(--seg-travel)' },
]

/** Stacked horizontal bar of mean minutes per stage, today vs optimised. */
export function Breakdown({ today, opt, showOpt }: { today: Stats; opt: Stats; showOpt: boolean }) {
  const reduce = useReducedMotion()
  const rows = showOpt ? [{ label: 'Today', s: today }, { label: 'Optimised', s: opt }] : [{ label: 'Today', s: today }]
  const max = Math.max(...rows.map((r) => r.s.ch + r.s.dp + r.s.tr))
  const W = 100
  return (
    <div>
      {rows.map((r) => {
        const total = r.s.ch + r.s.dp + r.s.tr
        let x = 0
        return (
          <div key={r.label} style={{ marginBottom: 14 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 6 }}>
              <span style={{ color: 'var(--text-2)' }}>{r.label}</span>
              <span className="num" style={{ fontWeight: 600 }}>
                {min1(total)} min average
              </span>
            </div>
            <svg viewBox={`0 0 ${W} 14`} preserveAspectRatio="none" style={{ height: 14 }} role="img"
              aria-label={`${r.label}: call handling ${min1(r.s.ch)}, dispatch ${min1(r.s.dp)}, travel ${min1(r.s.tr)} minutes`}>
              {SEG.map((seg) => {
                const w = (W * r.s[seg.key]) / max
                const el = (
                  <motion.rect
                    key={seg.key}
                    y={0}
                    height={14}
                    fill={seg.color}
                    initial={false}
                    animate={{ x, width: Math.max(0, w - 0.6) }}
                    transition={{ duration: reduce ? 0 : 0.3, ease: [0.22, 1, 0.36, 1] }}
                  />
                )
                x += w
                return el
              })}
            </svg>
            <div style={{ display: 'flex', gap: 14, fontSize: 13, marginTop: 6 }} className="num">
              {SEG.map((seg) => (
                <span key={seg.key} style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-2)' }}>
                  <i style={{ width: 8, height: 8, borderRadius: 2, background: seg.color, display: 'inline-block' }} />
                  {seg.label}
                  <b style={{ color: 'var(--text)', fontWeight: 600 }}>{min1(r.s[seg.key])}</b>
                </span>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

/** Small line of mean calls per hour of week: actual and forecast. */
export function DemandLine({ actual, forecast, how }: { actual: number[]; forecast: number[]; how: number }) {
  const W = 340
  const H = 120
  const m = { t: 8, r: 8, b: 20, l: 30 }
  const x = d3.scaleLinear([0, 167], [m.l, W - m.r])
  const ymax = d3.max([...actual, ...forecast]) ?? 1
  const y = d3.scaleLinear([0, ymax * 1.1], [H - m.b, m.t]).nice()
  const line = d3
    .line<number>()
    .x((_, i) => x(i))
    .y((v) => y(v))
    .curve(d3.curveMonotoneX)
  const ticks = y.ticks(3)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Life-threatening calls per hour of week, actual and forecast">
      <g className="axis">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={m.l} x2={W - m.r} y1={y(t)} y2={y(t)} />
            <text x={m.l - 6} y={y(t)} dy="0.32em" textAnchor="end">
              {t < 1 ? t.toFixed(1) : t}
            </text>
          </g>
        ))}
        {DAYS.map((d, i) => (
          <text key={d} x={x(i * 24 + 12)} y={H - 4} textAnchor="middle">
            {d}
          </text>
        ))}
      </g>
      <line x1={x(how)} x2={x(how)} y1={m.t} y2={H - m.b} stroke="#1d1d1f" strokeWidth={1} strokeDasharray="2 3" />
      <path d={line(forecast) ?? ''} fill="none" stroke="var(--seg-dispatch)" strokeWidth={1.5} />
      <path d={line(actual) ?? ''} fill="none" stroke="#1d1d1f" strokeWidth={1.5} />
    </svg>
  )
}

/** Borough fairness: median response Today vs Optimised side by side. */
export function Fairness({ rows, sev, highlight }: { rows: BoroughRow[]; sev: Sev; highlight?: string }) {
  const reduce = useReducedMotion()
  const W = 340
  const rowH = 34
  const m = { t: 4, r: 40, b: 22, l: 98 }
  const H = m.t + rows.length * rowH + m.b
  const max = d3.max(rows, (r) => Math.max(r[sev].today.median, r[sev].opt.median)) ?? 10
  const x = d3.scaleLinear([0, max * 1.05], [m.l, W - m.r]).nice()
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Median response by borough, today and with optimised staging">
      <g className="axis">
        {x.ticks(4).map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={m.t} y2={H - m.b} />
            <text x={x(t)} y={H - 6} textAnchor="middle">
              {t}
            </text>
          </g>
        ))}
        <text x={W - m.r + 36} y={H - 6} textAnchor="end">
          min
        </text>
      </g>
      {rows.map((r, i) => {
        const y0 = m.t + i * rowH
        const t = r[sev].today.median
        const o = r[sev].opt.median
        const on = highlight && titleCase(highlight) === titleCase(r.name)
        return (
          <g key={r.name}>
            <text x={0} y={y0 + 15} fontSize={13} fill="var(--text)" fontWeight={on ? 600 : 400}>
              {titleCase(r.name)}
            </text>
            <motion.rect x={m.l} y={y0 + 4} height={10} rx={2} fill="#8e8e93" initial={false}
              animate={{ width: x(t) - m.l }} transition={{ duration: reduce ? 0 : 0.3 }} />
            <motion.rect x={m.l} y={y0 + 16} height={10} rx={2} fill="var(--green)" initial={false}
              animate={{ width: x(o) - m.l }} transition={{ duration: reduce ? 0 : 0.3 }} />
            <text x={x(t) + 5} y={y0 + 13} fontSize={11} fill="var(--text-2)" className="num">
              {min1(t)}
            </text>
            <text x={x(o) + 5} y={y0 + 25} fontSize={11} fill="var(--green-text)" className="num" fontWeight={600}>
              {min1(o)}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

/** Hour x weekday heatmap. */
export function Heatmap({
  values,
  title,
  caption,
  diverging,
  max,
}: {
  values: number[]
  title: string
  caption: string
  diverging?: boolean
  max: number
}) {
  const W = 360
  const m = { t: 4, r: 4, b: 18, l: 30 }
  const cw = (W - m.l - m.r) / 24
  const ch = 13
  const H = m.t + 7 * ch + m.b
  const seq = d3.scaleSequential(d3.interpolateRgb('#fdf4f4', '#b4252a')).domain([0, max])
  const div = d3.scaleDiverging(d3.interpolateRgbBasis(['#5e5ce6', '#ffffff', '#e5484d'])).domain([-max, 0, max])
  return (
    <div className="inner heat">
      <div className="label" style={{ marginBottom: 2, color: 'var(--text)' }}>
        {title}
      </div>
      <div className="caption" style={{ marginBottom: 8 }}>
        {caption}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={title}>
        {values.map((v, i) => {
          const d = Math.floor(i / 24)
          const h = i % 24
          return (
            <rect key={i} x={m.l + h * cw} y={m.t + d * ch} width={cw - 1} height={ch - 1} rx={1.5}
              fill={diverging ? div(v) : seq(v)}>
              <title>{`${DAYS[d]} ${String(h).padStart(2, '0')}:00 · ${v.toFixed(2)}`}</title>
            </rect>
          )
        })}
        <g className="axis">
          {DAYS.map((d, i) => (
            <text key={d} x={m.l - 6} y={m.t + i * ch + ch / 2} dy="0.32em" textAnchor="end">
              {d}
            </text>
          ))}
          {[0, 6, 12, 18, 23].map((h) => (
            <text key={h} x={m.l + h * cw + cw / 2} y={H - 4} textAnchor="middle">
              {String(h).padStart(2, '0')}
            </text>
          ))}
        </g>
      </svg>
    </div>
  )
}
