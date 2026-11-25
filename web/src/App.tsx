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
import { blockOf, savedText } from './lib/format'
import {
  planFromQuery,
  planLayer,
  planStats,
  planToQuery,
  preset,
  type Comp,
  type Plan,
  type PlanData,
} from './lib/plan'
import type { BoroughRow, Demand, MapLayer, Sev, Staging, Stats, Summary, View, ZipDetail } from './lib/types'

const forSev = (comps: Comp[], sev: Sev) => (sev === 'lt' ? comps.filter((c) => c.cls === 'lt') : comps)

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
  const pd = useJson<PlanData>('plan.json')
  const pz = useJson<Comp[]>(view === 'opt' || selected ? 'plan_zip.json' : null)
  const [planState, setPlan] = useState<Plan | null>(null)
  const plan = useMemo(
    () => planState ?? (pd ? (planFromQuery(pd, new URLSearchParams(window.location.search)) ?? preset(pd, 'combined')) : null),
    [planState, pd],
  )
  const baseLayer = useJson<MapLayer>(layerName(view === 'opt' && plan?.staging ? 'opt' : 'today', sev))

  // keep the URL in step so any view, zip or plan can be shared as a link
  useEffect(() => {
    const q = new URLSearchParams()
    q.set('view', view)
    q.set('sev', sev)
    q.set('how', String(how))
    if (selected) q.set('zip', selected)
    if (drawer) q.set('drawer', '1')
    if (pd && plan) for (const [k, v] of Object.entries(planToQuery(pd, plan))) q.set(k, v)
    window.history.replaceState(null, '', `${window.location.pathname}?${q}`)
  }, [view, sev, how, selected, drawer, pd, plan])

  const zipBorough = useMemo(
    () => Object.fromEntries(Object.entries(details ?? {}).map(([z, d]) => [z, d.borough])),
    [details],
  )
  const zipComps = useMemo(() => {
    const m: Record<string, Comp[]> = {}
    for (const c of pz ?? []) (m[c.modzcta!] ??= []).push(c)
    return m
  }, [pz])

  const withPlan = useCallback(
    (today: Stats, comps: Comp[] | undefined, borough?: string): Stats =>
      pd && plan && comps?.length ? planStats(pd, plan, forSev(comps, sev), today, borough) : today,
    [pd, plan, sev],
  )

  const cityStats = useMemo(() => {
    if (!summary) return null
    const today = summary.city[sev].today
    return { today, opt: withPlan(today, pd?.comps) }
  }, [summary, sev, pd, withPlan])

  const boroughRows = useMemo<BoroughRow[]>(() => {
    if (!summary) return []
    return summary.boroughs.map((r) => {
      const comps = pd?.comps.filter((c) => c.borough === r.name)
      const lt = pd && plan && comps?.length ? planStats(pd, plan, forSev(comps, 'lt'), r.lt.today) : r.lt.today
      const all = pd && plan && comps?.length ? planStats(pd, plan, comps, r.all.today) : r.all.today
      return { name: r.name, lt: { today: r.lt.today, opt: lt }, all: { today: r.all.today, opt: all } }
    })
  }, [summary, pd, plan])

  const zipStats = useCallback(
    (id: string | null) => {
      const d = id ? details?.[id] : null
      const s = d?.[sev]
      if (!id || !d || !s) return null
      return { today: s.today, opt: withPlan(s.today, zipComps[id], d.borough) }
    },
    [details, sev, zipComps, withPlan],
  )

  const layer = useMemo(
    () => (view === 'opt' && pd && plan && baseLayer ? planLayer(pd, plan, baseLayer, zipBorough, sev) : baseLayer),
    [view, pd, plan, baseLayer, zipBorough, sev],
  )

  useEffect(() => {
    prefetchLayers()
  }, [])

  const select = useCallback((z: string | null) => {
    setSelected((cur) => (z && details && !details[z] ? cur : z))
  }, [details])

  const islandZipId = hoverZip ?? selected
  const islandZip = useMemo(() => {
    const st = zipStats(islandZipId)
    if (!islandZipId || !st || !details) return null
    return { id: islandZipId, borough: details[islandZipId].borough, ...st }
  }, [islandZipId, details, zipStats])

  const saved = cityStats ? cityStats.today.median - cityStats.opt.median : 0
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
            label="Scenario"
            value={view}
            onChange={setView}
            options={[
              { value: 'today', label: 'Today' },
              { value: 'opt', label: 'With plan' },
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
              <span className="headline-value num" aria-label={`${savedText(saved)} saved`}>
                −<Roller value={savedText(saved)} />
              </span>
              <span className="headline-caption">
                <span>median saved per {sev === 'lt' ? 'life-threatening call' : 'call'}</span>
                <span>
                  {view === 'opt' ? 'With your plan' : 'With the plan'} · 2025 ·{' '}
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
              showStaging={view === 'opt' && !!plan?.staging}
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
                  city={cityStats ?? summary.city[sev]}
                  zip={islandZip}
                  avoid={hoverZip ? rects.hover : rects.selected}
                  frameWidth={rects.width}
                />
              )}
              <Legend domain={domain} showStaging={view === 'opt' && !!plan?.staging} minN={summary?.min_n ?? 20} />
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
        {summary && details && cityStats ? (
          <RightPanel
            summary={summary}
            details={details}
            demand={demand}
            view={view}
            sev={sev}
            how={how}
            selected={selected}
            onSelect={select}
            pd={pd}
            plan={plan ?? { units: {}, cut: 0, staging: false }}
            onPlan={setPlan}
            zipStats={zipStats(selected)}
            cityStats={cityStats ?? summary.city[sev]}
            boroughRows={boroughRows}
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
