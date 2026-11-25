export const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
export const DAYS_LONG = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

export const min1 = (v: number | null | undefined) => (v == null || Number.isNaN(v) ? '–' : v.toFixed(1))

export const howLabel = (how: number) => `${DAYS[Math.floor(how / 24)]} ${String(how % 24).padStart(2, '0')}:00`
export const howLabelLong = (how: number) =>
  `${DAYS_LONG[Math.floor(how / 24)]} ${String(how % 24).padStart(2, '0')}:00–${String(how % 24).padStart(2, '0')}:59`

export const blockOf = (how: number) => Math.floor(how / 24) * 6 + Math.floor((how % 24) / 4)

export const titleCase = (s: string) =>
  s
    .toLowerCase()
    .replace('richmond / staten island', 'staten island')
    .replace(/\b\w/g, (c) => c.toUpperCase())

export const int = (v: number) => Math.round(v).toLocaleString('en-US')

export const pct = (v: number, d = 0) => `${(v * 100).toFixed(d)}%`

/** Saving label: seconds when under a minute (e.g. "4 s"), otherwise minutes to 1 decimal. */
export const savedText = (min: number) => {
  if (!Number.isFinite(min) || min <= 0) return '0\u00a0s'
  return min < 1 ? `${Math.round(min * 60)}\u00a0s` : `${min.toFixed(1)}\u00a0min`
}

export const savedChip = (min: number) => (Math.round(min * 60) <= 0 ? 'No change' : `−${savedText(min)}`)

/** Seconds under a minute, otherwise minutes to one decimal. */
export const secText = (min: number) =>
  Math.abs(min) < 1 ? `${Math.round(min * 60)}\u00a0s` : `${min.toFixed(1)}\u00a0min`
