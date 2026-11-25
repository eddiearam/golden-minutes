import { AnimatePresence } from 'framer-motion'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { AboutSheet } from './components/AboutSheet'
import { Drawer } from './components/Drawer'
import { HourSlider } from './components/HourSlider'
import { Island, type Rect } from './components/Island'
import { Legend } from './components/Legend'
import { MapView } from './components/MapView'
import { RightPanel } from './components/RightPanel'
import { Roller } from './components/Roller'
import { Segmented } from './components/Segmented'
import { layerName, prefetchLayers, useJson } from './lib/data'
import { blockOf, min1 } from './lib/format'
import type { Demand, MapLayer, Sev, Staging, Summary, View, ZipDetail } from './lib/types'

function initialParams() {
  const q = new URLSearchParams(window.location.search)
  const how = Number(q.get('how'))
  return {
    view: (q.get('view') === 'opt' ? 'opt' : 'today') as View,
    sev: (q.get('sev') === 'all' ? 'all' : 'lt') as Sev,
    how: Number.isInteger(how) && how >= 0 && how < 168 && q.has("how") ? how : 18, // Mon 18:00
    zip: q.get('zip'),
    drawer: q.get('drawer') === '1',
  }
}

export default function App() {
  const init = useMemo(initialParams, [])
  const [view, setView] = useState<View>(init.view)
  const [sev, setSev] = useState<Sev>(init.sev)
  const [how, setHow] = useState(init.how)
  const [playing, setPlaying] = useState(false)
  const [selected, setSelected] = useState<string | null>(init.zip)
  const [hoverZip, setHoverZip] = useState<string | null>(null)
  const [drawer, setDrawer] = useState(init.drawer)
  const [about, setAbout] = useState(false)
  const [rects, setRects] = useState<{ hover: Rect | null; selected: Rect | null; width: number }>({
    hover: null,
    selected: null,
    width: 0,
  })

  const summary = useJson<Summary>('summary.json')
  const geo = useJson<GeoJSON.FeatureCollection>('zips.geojson')
  const boroughs = useJson<GeoJSON.FeatureCollection>('boroughs.geojson')
  const details = useJson<Record<string, ZipDetail>>('zip_detail.json')
  const staging = useJson<Staging>('staging.json')
  const demand = useJson<Demand>('demand.json')
  const layer = useJson<MapLayer>(layerName(view, sev))

  useEffect(() => {
    prefetchLayers()
  }, [])

  const select = useCallback((z: string | null) => {
    setSelected((cur) => (z && details && !details[z] ? cur : z))
  }, [details])

  const islandZipId = hoverZip ?? selected
  const islandZip = useMemo(() => {
    if (!islandZipId || !details?.[islandZipId]) return null
    const d = details[islandZipId]
    const s = d[sev]
    if (!s) return null
    return { id: islandZipId, borough: d.borough, today: s.today, opt: s.opt }
  }, [islandZipId, details, sev])

  const saved = summary ? summary.city[sev].today.median - summary.city[sev].opt.median : 0
  const stagingPts = staging && summary ? staging[String(summary.k_default)][String(blockOf(how))] : null
  const domain = summary ? summary.scale[sev] : ([5, 15] as [number, number])

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden>
            <span />
          </span>
          Golden Minutes
        </div>
        <div className="controls">
          <Segmented
            label="Positioning"
            value={view}
            onChange={setView}
            options={[
              { value: 'today', label: 'Today' },
              { value: 'opt', label: 'Optimised staging' },
            ]}
          />
          <Segmented
            label="Call severity"
            value={sev}
            onChange={setSev}
            options={[
              { value: 'all', label: 'All' },
              { value: 'lt', label: 'Life-threatening' },
            ]}
          />
        </div>
        <div className="headline">
          {summary ? (
            <>
              <span className="headline-value num" aria-label={`${min1(saved)} minutes saved`}>
                −<Roller value={min1(saved)} />
              </span>
              <span className="headline-caption">
                <span>median minutes saved</span>
                <span>
                  {summary.k_default} staging points · 2025 ·{' '}
                  <button className="about-link" onClick={() => setAbout(true)}>
                    About the data
                  </button>
                </span>
              </span>
            </>
          ) : (
            <div className="skel" style={{ width: 220, height: 36 }} />
          )}
        </div>
      </header>

      <main className="main">
        <div className="map-col">
          <div className="card map-card">
            <MapView
              geo={geo}
              boroughs={boroughs}
              layer={layer}
              how={how}
              domain={domain}
              staging={stagingPts}
              showStaging={view === 'opt'}
              selected={selected}
              hoverZip={hoverZip}
              onHover={setHoverZip}
              onSelect={select}
              onRects={setRects}
              minN={summary?.min_n ?? 20}
            >
              {summary && (
                <Island
                  view={view}
                  sev={sev}
                  city={summary.city[sev]}
                  zip={islandZip}
                  avoid={hoverZip ? rects.hover : rects.selected}
                  frameWidth={rects.width}
                />
              )}
              <Legend domain={domain} showStaging={view === 'opt'} minN={summary?.min_n ?? 20} />
              <HourSlider how={how} onChange={setHow} playing={playing} onPlay={setPlaying} />
            </MapView>
          </div>
          {summary && (
            <Drawer
              open={drawer}
              onToggle={() => setDrawer((o) => !o)}
              demand={demand}
              zip={selected}
              mae={summary.forecast}
            />
          )}
        </div>
        {summary && details ? (
          <RightPanel
            summary={summary}
            details={details}
            demand={demand}
            view={view}
            sev={sev}
            how={how}
            selected={selected}
            onSelect={select}
          />
        ) : (
          <aside className="panel">
            <div className="card panel-card">
              <div className="skel" style={{ height: 44 }} />
              <div className="skel" style={{ height: 28, width: '60%', marginTop: 20 }} />
              <div className="skel" style={{ height: 96, marginTop: 16 }} />
              <div className="skel" style={{ height: 160, marginTop: 12 }} />
            </div>
          </aside>
        )}
      </main>
      <AnimatePresence>{about && summary && <AboutSheet summary={summary} onClose={() => setAbout(false)} />}</AnimatePresence>
    </div>
  )
}
