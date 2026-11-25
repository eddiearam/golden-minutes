import { useEffect, useState } from 'react'
import type { Demand, MapLayer, Sev, Staging, Summary, View, ZipDetail } from './types'

const base = `${import.meta.env.BASE_URL}data/`
const cache = new Map<string, Promise<unknown>>()

export function fetchJson<T>(name: string): Promise<T> {
  if (!cache.has(name)) {
    cache.set(
      name,
      fetch(base + name).then((r) => {
        if (!r.ok) throw new Error(`${name}: ${r.status}`)
        return r.json()
      }),
    )
  }
  return cache.get(name) as Promise<T>
}

export function useJson<T>(name: string | null): T | null {
  const [data, setData] = useState<{ name: string; value: T } | null>(null)
  useEffect(() => {
    if (!name) return
    let live = true
    fetchJson<T>(name).then((v) => live && setData({ name, value: v }))
    return () => {
      live = false
    }
  }, [name])
  return data && data.name === name ? data.value : null
}

export const layerName = (view: View, sev: Sev) => `map_${view}_${sev}.json`

export function prefetchLayers() {
  for (const v of ['today', 'opt'] as View[]) for (const s of ['lt', 'all'] as Sev[]) fetchJson<MapLayer>(layerName(v, s))
}

export type { Demand, MapLayer, Staging, Summary, ZipDetail }
