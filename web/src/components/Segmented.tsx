import { motion } from 'framer-motion'
import { useId, useRef } from 'react'

interface Props<T extends string> {
  label: string
  value: T
  options: { value: T; label: string }[]
  onChange: (v: T) => void
}

export function Segmented<T extends string>({ label, value, options, onChange }: Props<T>) {
  const id = useId()
  const refs = useRef<(HTMLButtonElement | null)[]>([])
  const idx = options.findIndex((o) => o.value === value)

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
    e.preventDefault()
    const next = (idx + (e.key === 'ArrowRight' ? 1 : options.length - 1)) % options.length
    onChange(options[next].value)
    refs.current[next]?.focus()
  }

  return (
    <div className="seg" role="radiogroup" aria-label={label} onKeyDown={onKey}>
      {options.map((o, i) => {
        const on = o.value === value
        return (
          <button
            key={o.value}
            ref={(el) => {
              refs.current[i] = el
            }}
            role="radio"
            aria-checked={on}
            tabIndex={on ? 0 : -1}
            onClick={() => onChange(o.value)}
          >
            {on && (
              <motion.span
                layoutId={`thumb-${id}`}
                className="seg-thumb"
                transition={{ type: 'spring', stiffness: 520, damping: 40 }}
              />
            )}
            {o.label}
          </button>
        )
      })}
    </div>
  )
}
