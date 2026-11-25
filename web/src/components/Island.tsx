import { AnimatePresence, LayoutGroup, motion, useReducedMotion } from 'framer-motion'
import { useLayoutEffect, useRef, useState } from 'react'
import { min1, titleCase } from '../lib/format'
import type { Sev, Stats, View } from '../lib/types'
import { Roller } from './Roller'

export interface Rect {
  left: number
  right: number
  top: number
  bottom: number
}

interface Props {
  view: View
  sev: Sev
  city: { today: Stats; opt: Stats }
  zip: { id: string; borough: string; today: Stats; opt: Stats } | null
  /** screen rect (relative to the map frame) of the zip to keep visible */
  avoid: Rect | null
  frameWidth: number
}

const SPRING = { type: 'spring' as const, duration: 0.35, bounce: 0.06 }
const SEGMENTS = [
  { key: 'ch' as const, label: 'Call handling', color: 'var(--seg-call)' },
  { key: 'dp' as const, label: 'Dispatch', color: 'var(--seg-dispatch)' },
  { key: 'tr' as const, label: 'Travel', color: 'var(--seg-travel)' },
]

export function Island({ view, sev, city, zip, avoid, frameWidth }: Props) {
  const reduce = useReducedMotion()
  const ref = useRef<HTMLDivElement>(null)
  const [align, setAlign] = useState<'center' | 'left' | 'right'>('center')
  const cur = view === 'opt' ? city.opt : city.today
  const saved = city.today.median - city.opt.median
  const expanded = zip != null
  const transition = reduce ? { duration: 0.15 } : SPRING

  // Keep the island off the zip: if the centred island would overlap it, slide to the far side.
  useLayoutEffect(() => {
    if (!avoid || !frameWidth) {
      setAlign('center')
      return
    }
    const w = expanded ? 340 : (ref.current?.offsetWidth ?? 300)
    const h = expanded ? 150 : 44
    const top = 16
    const overlaps = (l: number) => !(avoid.right < l || avoid.left > l + w || avoid.top > top + h || avoid.bottom < top)
    const centreLeft = (frameWidth - w) / 2
    if (!overlaps(centreLeft)) setAlign('center')
    else if (!overlaps(16)) setAlign('left')
    else setAlign('right')
  }, [avoid, frameWidth, expanded])

  const justify = align === 'center' ? 'center' : align === 'left' ? 'flex-start' : 'flex-end'

  return (
    <div
      className="float island-wrap"
      style={{ left: 16, right: 16, transform: 'none', justifyContent: justify }}
      aria-live="polite"
    >
      <LayoutGroup>
        <motion.div
          ref={ref}
          layout
          className="island"
          style={{ borderRadius: expanded ? 24 : 999 }}
          transition={{ layout: transition, borderRadius: transition }}
          data-testid="island"
          data-state={expanded ? 'expanded' : 'pill'}
        >
          <AnimatePresence mode="popLayout" initial={false}>
            {expanded && zip ? (
              <motion.div
                key="card"
                className="island-card"
                initial={{ opacity: 0, filter: reduce ? 'none' : 'blur(4px)' }}
                animate={{ opacity: 1, filter: 'blur(0px)' }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2, delay: reduce ? 0 : 0.08 }}
              >
                <ZipCard zip={zip} view={view} sev={sev} reduce={!!reduce} />
              </motion.div>
            ) : (
              <motion.div
                key="pill"
                className="island-pill"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.18 }}
              >
                <span className="island-dot" aria-hidden />
                <span>NYC</span>
                <span className="island-sep">·</span>
                <span>{sev === 'lt' ? 'Life-threatening' : 'All calls'}</span>
                <span className="island-sep">·</span>
                <span>
                  Median <Roller value={min1(cur.median)} /> min
                </span>
                <AnimatePresence>
                  {view === 'opt' && (
                    <motion.span
                      className="chip-saved num"
                      initial={{ opacity: 0, width: 0, marginLeft: -8 }}
                      animate={{ opacity: 1, width: 'auto', marginLeft: 0 }}
                      exit={{ opacity: 0, width: 0, marginLeft: -8 }}
                      transition={{ duration: 0.25 }}
                    >
                      −{min1(saved)} min
                    </motion.span>
                  )}
                </AnimatePresence>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      </LayoutGroup>
    </div>
  )
}

function ZipCard({
  zip,
  view,
  sev,
  reduce,
}: {
  zip: NonNullable<Props['zip']>
  view: View
  sev: Sev
  reduce: boolean
}) {
  const s = view === 'opt' ? zip.opt : zip.today
  const total = s.ch + s.dp + s.tr
  const saved = zip.today.median - zip.opt.median
  return (
    <>
      <div className="island-top">
        <span className="island-zip">ZIP {zip.id}</span>
        <span className="island-boro">
          {titleCase(zip.borough)} · {sev === 'lt' ? 'Life-threatening' : 'All calls'}
        </span>
      </div>
      <div className="island-stats">
        <div className="island-stat">
          <div className="k">Median</div>
          <div className="v num">
            <Roller value={min1(s.median)} />
            <small>min</small>
          </div>
        </div>
        <div className="island-stat">
          <div className="k">90th percentile</div>
          <div className="v num">
            <Roller value={min1(s.p90)} />
            <small>min</small>
          </div>
        </div>
        {view === 'opt' && (
          <div className="island-stat" style={{ alignSelf: 'flex-end', paddingBottom: 4 }}>
            <span className="chip-saved num">−{min1(saved)} min</span>
          </div>
        )}
      </div>
      <div className="mini-bar" role="img" aria-label={`Average: call handling ${min1(s.ch)}, dispatch ${min1(s.dp)}, travel ${min1(s.tr)} minutes`}>
        {SEGMENTS.map((seg, i) => (
          <motion.span
            key={`${zip.id}-${seg.key}`}
            style={{ background: seg.color, width: `${(100 * s[seg.key]) / total}%`, transformOrigin: 'left' }}
            initial={{ scaleX: reduce ? 1 : 0 }}
            animate={{ scaleX: 1 }}
            transition={{ duration: reduce ? 0 : 0.4 / 3, delay: reduce ? 0 : 0.12 + (i * 0.4) / 3, ease: 'linear' }}
          />
        ))}
      </div>
      <div className="mini-legend num">
        {SEGMENTS.map((seg) => (
          <span key={seg.key}>
            <i style={{ background: seg.color }} />
            {seg.label} {min1(s[seg.key])}
          </span>
        ))}
      </div>
    </>
  )
}
