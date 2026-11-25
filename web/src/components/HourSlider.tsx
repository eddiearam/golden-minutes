import { useEffect } from 'react'
import { DAYS, howLabelLong } from '../lib/format'

interface Props {
  how: number
  onChange: (h: number) => void
  playing: boolean
  onPlay: (p: boolean) => void
}

export function HourSlider({ how, onChange, playing, onPlay }: Props) {
  useEffect(() => {
    if (!playing) return
    const t = window.setInterval(() => onChange((how + 1) % 168), 450)
    return () => window.clearInterval(t)
  }, [playing, how, onChange])

  return (
    <div className="float card slider-card">
      <button
        className="play"
        aria-pressed={playing}
        aria-label={playing ? 'Pause the week' : 'Play through the week'}
        onClick={() => onPlay(!playing)}
      >
        {playing ? (
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden>
            <rect x="2" y="1.5" width="2.6" height="9" rx="1" fill="#1d1d1f" />
            <rect x="7.4" y="1.5" width="2.6" height="9" rx="1" fill="#1d1d1f" />
          </svg>
        ) : (
          <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden>
            <path d="M3 1.8v8.4a.6.6 0 0 0 .9.5l6.8-4.2a.6.6 0 0 0 0-1L3.9 1.3a.6.6 0 0 0-.9.5Z" fill="#1d1d1f" />
          </svg>
        )}
      </button>
      <div className="slider-body">
        <div className="slider-head">
          <strong className="num">{howLabelLong(how)}</strong>
          <span className="caption">Hour of week · 2025</span>
        </div>
        <input
          className="range"
          type="range"
          min={0}
          max={167}
          step={1}
          value={how}
          aria-label="Hour of week"
          aria-valuetext={howLabelLong(how)}
          onChange={(e) => {
            onPlay(false)
            onChange(Number(e.target.value))
          }}
        />
        <div className="day-ticks" aria-hidden>
          {DAYS.map((d) => (
            <span key={d}>{d}</span>
          ))}
        </div>
      </div>
    </div>
  )
}
