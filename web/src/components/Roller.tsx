import { motion, useReducedMotion } from 'framer-motion'

/** Rolls each digit to its new value. Non-digit characters are shown as is. */
export function Roller({ value, className }: { value: string; className?: string }) {
  const reduce = useReducedMotion()
  const chars = value.split('')
  return (
    <span className={`roller num ${className ?? ''}`} aria-label={value}>
      {chars.map((c, i) => {
        const key = chars.length - i // align from the right so units stay put
        if (!/\d/.test(c)) {
          return (
            <span key={`s${key}`} aria-hidden style={c === '\u00a0' ? { width: '0.28em' } : undefined}>
              {c}
            </span>
          )
        }
        const d = Number(c)
        return (
          <span key={`d${key}`} className="roller-digit" aria-hidden>
            <motion.span
              className="roller-col"
              initial={false}
              animate={{ y: `${-d * 1.2}em` }}
              transition={
                reduce ? { duration: 0 } : { type: 'spring', stiffness: 260, damping: 30, delay: (chars.length - i) * 0.03 }
              }
            >
              {Array.from({ length: 10 }, (_, n) => (
                <span key={n} style={{ height: '1.2em' }}>
                  {n}
                </span>
              ))}
            </motion.span>
          </span>
        )
      })}
    </span>
  )
}
