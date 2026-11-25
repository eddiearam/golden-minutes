import { useId, useMemo, useState } from 'react'
import { titleCase } from '../lib/format'

export function ZipSearch({
  zips,
  onSelect,
}: {
  zips: { id: string; borough: string }[]
  onSelect: (z: string) => void
}) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const listId = useId()
  const matches = useMemo(() => {
    const s = q.trim().toLowerCase()
    if (!s) return []
    return zips.filter((z) => z.id.startsWith(s) || titleCase(z.borough).toLowerCase().startsWith(s)).slice(0, 8)
  }, [q, zips])

  const choose = (z: string) => {
    onSelect(z)
    setQ('')
    setOpen(false)
  }

  return (
    <div className="search">
      <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden>
        <circle cx="7" cy="7" r="5" fill="none" stroke="#636366" strokeWidth="1.6" />
        <path d="m11 11 3.5 3.5" stroke="#636366" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
      <input
        value={q}
        placeholder="Search a zip code"
        inputMode="numeric"
        aria-label="Search a zip code"
        role="combobox"
        aria-expanded={open && matches.length > 0}
        aria-controls={listId}
        aria-activedescendant={matches[active] ? `${listId}-${matches[active].id}` : undefined}
        onChange={(e) => {
          setQ(e.target.value)
          setActive(0)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') {
            e.preventDefault()
            setActive((a) => Math.min(a + 1, matches.length - 1))
          } else if (e.key === 'ArrowUp') {
            e.preventDefault()
            setActive((a) => Math.max(a - 1, 0))
          } else if (e.key === 'Enter') {
            const exact = zips.find((z) => z.id === q.trim())
            const pick = exact?.id ?? matches[active]?.id
            if (pick) choose(pick)
          } else if (e.key === 'Escape') {
            setOpen(false)
          }
        }}
      />
      {open && matches.length > 0 && (
        <ul className="search-list" role="listbox" id={listId}>
          {matches.map((z, i) => (
            <li
              key={z.id}
              id={`${listId}-${z.id}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => {
                e.preventDefault()
                choose(z.id)
              }}
              onMouseEnter={() => setActive(i)}
            >
              <span className="num">{z.id}</span>
              <span>{titleCase(z.borough)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
