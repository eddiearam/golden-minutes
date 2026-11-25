import maplibregl, { type GeoJSONSource, type Map as MLMap } from 'maplibre-gl'
import { useCallback, useEffect, useRef, useState } from 'react'
import { min1 } from '../lib/format'
import type { MapLayer } from '../lib/types'
import type { Rect } from './Island'

import { SCALE } from '../lib/scale'

interface Props {
  geo: GeoJSON.FeatureCollection | null
  boroughs: GeoJSON.FeatureCollection | null
  layer: MapLayer | null
  how: number
  domain: [number, number]
  staging: [number, number, string][] | null
  showStaging: boolean
  selected: string | null
  onHover: (zip: string | null) => void
  onSelect: (zip: string | null) => void
  onRects: (r: { hover: Rect | null; selected: Rect | null; width: number }) => void
  hoverZip: string | null
  minN: number
  children?: React.ReactNode
}

const BOUNDS: [[number, number], [number, number]] = [
  [-74.27, 40.49],
  [-73.69, 40.92],
]

function hatchImage(): ImageData {
  const s = 8
  const c = document.createElement('canvas')
  c.width = c.height = s
  const g = c.getContext('2d')!
  g.fillStyle = '#f2f2f4'
  g.fillRect(0, 0, s, s)
  g.strokeStyle = '#c7c7cc'
  g.lineWidth = 1.5
  g.beginPath()
  g.moveTo(0, s)
  g.lineTo(s, 0)
  g.moveTo(-s / 2, s / 2)
  g.lineTo(s / 2, -s / 2)
  g.moveTo(s / 2, s * 1.5)
  g.lineTo(s * 1.5, s / 2)
  g.stroke()
  return g.getImageData(0, 0, s, s)
}

export function MapView(p: Props) {
  const box = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MLMap | null>(null)
  const [ready, setReady] = useState(false)
  const [failed, setFailed] = useState(false)
  const shown = useRef<Map<string, number | null>>(new Map())
  const anim = useRef<number>(0)
  const hoverId = useRef<string | null>(null)
  const bboxes = useRef<Map<string, [number, number, number, number]>>(new Map())
  const [tip, setTip] = useState<{ x: number; y: number; zip: string } | null>(null)
  const props = useRef(p)
  props.current = p

  // ---- create map once geometry is available
  useEffect(() => {
    if (!box.current || !p.geo || !p.boroughs || mapRef.current) return
    for (const f of p.geo.features) {
      const id = String(f.properties!.modzcta)
      let [a, b, c, d] = [180, 90, -180, -90]
      const walk = (x: unknown): void => {
        if (Array.isArray(x) && typeof x[0] === 'number') {
          a = Math.min(a, x[0] as number)
          c = Math.max(c, x[0] as number)
          b = Math.min(b, x[1] as number)
          d = Math.max(d, x[1] as number)
        } else if (Array.isArray(x)) x.forEach(walk)
      }
      walk((f.geometry as GeoJSON.Polygon).coordinates)
      bboxes.current.set(id, [a, b, c, d])
    }
    let map: MLMap
    try {
      map = new maplibregl.Map({
      container: box.current,
      style: {
        version: 8,
        sources: {},
        layers: [{ id: 'water', type: 'background', paint: { 'background-color': '#e8f1f8' } }],
      },
      bounds: BOUNDS,
      fitBoundsOptions: { padding: { top: 72, bottom: 112, left: 24, right: 24 } },
      maxBounds: [
        [-74.6, 40.35],
        [-73.35, 41.05],
      ],
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
      attributionControl: false,
      fadeDuration: 0,
      })
    } catch {
      // WebGL unavailable (blocked by a browser privacy setting or switched off): keep the rest of the page
      setFailed(true)
      return
    }
    map.getCanvas().addEventListener('webglcontextlost', () => setFailed(true))
    map.touchZoomRotate.disableRotation()
    map.keyboard.disableRotation()
    mapRef.current = map
    map.on('load', () => {
      map.addImage('hatch', hatchImage(), { pixelRatio: 2 })
      map.addSource('zips', { type: 'geojson', data: p.geo!, promoteId: 'modzcta' })
      map.addSource('boroughs', { type: 'geojson', data: p.boroughs! })
      map.addSource('staging', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
      const [lo, hi] = props.current.domain
      map.addLayer({
        id: 'zip-fill',
        type: 'fill',
        source: 'zips',
        paint: {
          'fill-color': colorExpr(lo, hi),
          'fill-opacity': 1,
        },
      })
      map.addLayer({
        id: 'zip-hatch',
        type: 'fill',
        source: 'zips',
        paint: {
          'fill-pattern': 'hatch',
          'fill-opacity': ['case', ['boolean', ['feature-state', 'nodata'], false], 1, 0],
        },
      })
      map.addLayer({
        id: 'zip-line',
        type: 'line',
        source: 'zips',
        paint: { 'line-color': '#ffffff', 'line-width': ['interpolate', ['linear'], ['zoom'], 9, 0.5, 13, 1.4] },
      })
      map.addLayer({
        id: 'borough-line',
        type: 'line',
        source: 'boroughs',
        paint: { 'line-color': '#6e6e73', 'line-width': ['interpolate', ['linear'], ['zoom'], 9, 0.9, 13, 2] },
      })
      map.addLayer({
        id: 'zip-hover',
        type: 'line',
        source: 'zips',
        paint: {
          'line-color': '#1d1d1f',
          'line-width': [
            'case',
            ['boolean', ['feature-state', 'selected'], false],
            2.5,
            ['boolean', ['feature-state', 'hover'], false],
            2,
            0,
          ],
          'line-opacity': ['case', ['boolean', ['feature-state', 'selected'], false], 1, 0.85],
        },
      })
      map.addLayer({
        id: 'staging-halo',
        type: 'circle',
        source: 'staging',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 9, 8, 13, 14],
          'circle-color': '#1d1d1f',
          'circle-opacity': 0.14,
          'circle-blur': 0.4,
        },
      })
      map.addLayer({
        id: 'staging-dot',
        type: 'circle',
        source: 'staging',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 9, 3.2, 13, 5],
          'circle-color': '#1d1d1f',
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 1.25,
        },
      })

      map.on('mousemove', 'zip-fill', (e) => {
        const f = e.features?.[0]
        if (!f) return
        const id = String(f.id)
        if (hoverId.current !== id) {
          if (hoverId.current) map.setFeatureState({ source: 'zips', id: hoverId.current }, { hover: false })
          hoverId.current = id
          map.setFeatureState({ source: 'zips', id }, { hover: true })
          props.current.onHover(id)
        }
        map.getCanvas().style.cursor = 'pointer'
        setTip({ x: e.point.x, y: e.point.y, zip: id })
      })
      map.on('mouseleave', 'zip-fill', () => {
        if (hoverId.current) map.setFeatureState({ source: 'zips', id: hoverId.current }, { hover: false })
        hoverId.current = null
        map.getCanvas().style.cursor = ''
        setTip(null)
        props.current.onHover(null)
      })
      map.on('click', (e) => {
        const f = map.queryRenderedFeatures(e.point, { layers: ['zip-fill'] })[0]
        props.current.onSelect(f ? String(f.id) : null)
      })
      map.on('move', () => reportRects())
      setReady(true)
    })
    const ro = new ResizeObserver(() => {
      map.resize()
      if (!props.current.selected) map.fitBounds(BOUNDS, { padding: { top: 72, bottom: 112, left: 24, right: 24 }, duration: 0 })
      reportRects()
    })
    ro.observe(box.current)
    return () => {
      ro.disconnect()
      map.remove()
      mapRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.geo, p.boroughs])

  const rectOf = useCallback((id: string | null): Rect | null => {
    const map = mapRef.current
    const bb = id ? bboxes.current.get(id) : null
    if (!map || !bb) return null
    const a = map.project([bb[0], bb[3]])
    const b = map.project([bb[2], bb[1]])
    return { left: a.x, top: a.y, right: b.x, bottom: b.y }
  }, [])

  const reportRects = useCallback(() => {
    const map = mapRef.current
    if (!map) return
    const cur = props.current
    cur.onRects({
      hover: rectOf(cur.hoverZip),
      selected: rectOf(cur.selected),
      width: map.getContainer().clientWidth,
    })
  }, [rectOf])

  useEffect(() => {
    reportRects()
  }, [p.hoverZip, p.selected, reportRects])

  // ---- colour domain
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    map.setPaintProperty('zip-fill', 'fill-color', colorExpr(p.domain[0], p.domain[1]))
  }, [ready, p.domain])

  // ---- values for the current layer and hour, tweened from what is on screen
  const lastLayer = useRef<MapLayer | null>(null)
  useEffect(() => {
    const map = mapRef.current
    const layer = p.layer
    if (!ready || !map || !layer) return
    const layerChanged = lastLayer.current !== layer
    lastLayer.current = layer
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const duration = reduce ? 0 : layerChanged ? 600 : 220
    const from = new Map(shown.current)
    const to = new Map<string, number | null>()
    layer.zips.forEach((z, i) => to.set(z, layer.median[i][p.how]))
    for (const [z, v] of to) map.setFeatureState({ source: 'zips', id: z }, { nodata: v == null })
    cancelAnimationFrame(anim.current)
    const t0 = performance.now()
    const step = (t: number) => {
      const k = duration ? Math.min(1, (t - t0) / duration) : 1
      const e = 1 - Math.pow(1 - k, 3)
      for (const [z, v] of to) {
        if (v == null) continue
        const a = from.get(z)
        const val = a == null ? v : a + (v - a) * e
        map.setFeatureState({ source: 'zips', id: z }, { v: val })
        shown.current.set(z, val)
      }
      if (k < 1) anim.current = requestAnimationFrame(step)
    }
    anim.current = requestAnimationFrame(step)
    for (const [z, v] of to) if (v == null) shown.current.set(z, null)
  }, [ready, p.layer, p.how])

  // ---- staging points
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    const src = map.getSource('staging') as GeoJSONSource
    src.setData({
      type: 'FeatureCollection',
      features: (p.staging ?? []).map(([lon, lat, zip]) => ({
        type: 'Feature',
        properties: { zip },
        geometry: { type: 'Point', coordinates: [lon, lat] },
      })),
    })
    const o = p.showStaging ? 1 : 0
    map.setPaintProperty('staging-dot', 'circle-opacity', o)
    map.setPaintProperty('staging-dot', 'circle-stroke-opacity', o)
    map.setPaintProperty('staging-halo', 'circle-opacity', 0.14 * o)
  }, [ready, p.staging, p.showStaging])

  // ---- selection: outline + gentle zoom that keeps the zip clear of the island
  const prevSel = useRef<string | null>(null)
  useEffect(() => {
    const map = mapRef.current
    if (!ready || !map) return
    if (prevSel.current) map.setFeatureState({ source: 'zips', id: prevSel.current }, { selected: false })
    prevSel.current = p.selected
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (p.selected) {
      map.setFeatureState({ source: 'zips', id: p.selected }, { selected: true })
      const bb = bboxes.current.get(p.selected)
      if (bb) {
        const curZoom = map.getZoom()
        map.fitBounds(
          [
            [bb[0], bb[1]],
            [bb[2], bb[3]],
          ],
          {
            padding: { top: 190, bottom: 140, left: 120, right: 120 },
            maxZoom: Math.max(curZoom, 11.4),
            duration: reduce ? 0 : 700,
          },
        )
      }
    } else {
      map.fitBounds(BOUNDS, { padding: { top: 72, bottom: 112, left: 24, right: 24 }, duration: reduce ? 0 : 700 })
    }
  }, [ready, p.selected])

  const tipRow = tip && p.layer ? p.layer.zips.indexOf(tip.zip) : -1
  const tipMed = tipRow >= 0 ? p.layer!.median[tipRow][p.how] : null
  const tipN = tipRow >= 0 ? p.layer!.n[tipRow][p.how] : 0

  return (
    <div className="map-frame">
      <div ref={box} className="map-canvas" aria-label="Map of New York City zip codes" role="region" />
      {!ready && !failed && <div className="skel" style={{ position: 'absolute', inset: 0, borderRadius: 12 }} />}
      {failed && (
        <div className="map-fallback" role="status">
          <strong>The map needs WebGL, which this browser has turned off.</strong>
          <span>
            Turn on graphics acceleration in the browser's settings (in Brave: Settings, System), restart the browser
            and reload. The panel and charts still work.
          </span>
        </div>
      )}
      {tip && (
        <div className="tooltip" style={{ left: tip.x, top: tip.y }}>
          <strong>ZIP {tip.zip}</strong>
          {tipMed != null ? (
            <>
              <div className="row num">
                <span>Median</span>
                <span>{min1(tipMed)} min</span>
              </div>
              <div className="row num">
                <span>Calls</span>
                <span>{tipN.toLocaleString('en-US')}</span>
              </div>
            </>
          ) : (
            <div className="row" style={{ display: 'block', maxWidth: 200, whiteSpace: 'normal' }}>
              Only {tipN} calls in this hour window in 2025; at least {p.minN} needed for a reliable median.
            </div>
          )}
        </div>
      )}
      {p.children}
    </div>
  )
}

function colorExpr(lo: number, hi: number): maplibregl.ExpressionSpecification {
  const stops: (number | string)[] = []
  SCALE.forEach((c, i) => stops.push(lo + ((hi - lo) * i) / (SCALE.length - 1), c))
  return [
    'case',
    ['boolean', ['feature-state', 'nodata'], false],
    '#f2f2f4',
    ['interpolate', ['linear'], ['to-number', ['feature-state', 'v'], lo], ...stops] as maplibregl.ExpressionSpecification,
  ]
}
