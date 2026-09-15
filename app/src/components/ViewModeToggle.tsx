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

// Horizontal segmented control with a sliding highlight (CSS transform
// transition, no library) — three real, equally-weighted states, not
// three small separate buttons. The highlight pill is absolutely
// positioned at 1/3 the track width and translated by index * 100%, so it
// slides under whichever label is active rather than each button toggling
// its own background independently.
export default function ViewModeToggle({ mode, onChange }: Props) {
  const activeIndex = MODES.findIndex(m => m.key === mode)

  return (
    <div
      className="relative inline-flex rounded"
      style={{ border: '1px solid var(--border)', padding: 2 }}
    >
      <div
        aria-hidden="true"
        className="absolute rounded"
        style={{
          top: 2, bottom: 2, left: 2,
          width: `calc((100% - 4px) / 3)`,
          background: 'var(--accent)',
          transform: `translateX(${activeIndex * 100}%)`,
          transition: 'transform 240ms ease',
        }}
      />
      {MODES.map(m => {
        const active = m.key === mode
        return (
          <button
            key={m.key}
            onClick={() => onChange(m.key)}
            className="relative z-10 px-4 py-1.5 text-xs font-medium transition-colors"
            style={{ color: active ? 'var(--bg)' : 'var(--text-body)', minWidth: 72 }}
          >
            {m.label}
          </button>
        )
      })}
    </div>
  )
}
