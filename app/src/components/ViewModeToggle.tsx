import type { ViewMode } from '../utils/viewMode'

const MODES: { key: ViewMode; label: string }[] = [
  { key: 'list',    label: 'List' },
  { key: 'grid',    label: 'Grid' },
  { key: 'compact', label: 'Compact' },
]

interface Props {
  mode: ViewMode
  onChange: (mode: ViewMode) => void
}

// Flat text-with-marker treatment (corrected direction) — NOT a pill/
// segmented control. Three plain letter-spaced uppercase words; the
// active one is --text-heading with a small solid triangle beneath it
// (the one sanctioned decorative use of --accent per Part 3 — an
// active-state marker, not a fill), inactive ones sit at --text-body.
export default function ViewModeToggle({ mode, onChange }: Props) {
  return (
    <div className="flex items-center gap-5">
      {MODES.map(m => {
        const active = m.key === mode
        return (
          <button
            key={m.key}
            onClick={() => onChange(m.key)}
            className="flex flex-col items-center gap-1 text-[11px] uppercase tracking-[0.12em] font-medium transition-colors"
            style={{ color: active ? 'var(--text-heading)' : 'var(--text-body)' }}
          >
            {m.label}
            <svg width="7" height="5" viewBox="0 0 7 5" aria-hidden="true" style={{ visibility: active ? 'visible' : 'hidden' }}>
              <path d="M3.5 5L0 0h7z" fill="var(--accent)" />
            </svg>
          </button>
        )
      })}
    </div>
  )
}
