// Custom inline SVG icons for the six evidence metrics — geometric,
// thin-stroke (1.5px), 16x16, currentColor. No icon library, per the
// Phase 1 design system's explicit prohibition on Lucide/any icon library.

type IconProps = { className?: string }

const base = {
  width: 16,
  height: 16,
  viewBox: '0 0 16 16',
  fill: 'none' as const,
  stroke: 'currentColor',
  strokeWidth: 1.5,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
}

// RNA — two parallel wavy strands
export function IconRNA({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <path d="M2 4c1.5 2 1.5-2 3-2s1.5 4 3 4 1.5-4 3-4 1.5 2 3 2" />
      <path d="M2 12c1.5 2 1.5-2 3-2s1.5 4 3 4 1.5-4 3-4 1.5 2 3 2" />
    </svg>
  )
}

// PROTEIN — a small chain of three linked circles
export function IconProtein({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <circle cx="3.5" cy="8" r="2" />
      <circle cx="8" cy="4.5" r="2" />
      <circle cx="12.5" cy="8" r="2" />
      <path d="M5.1 6.9 6.4 5.8M9.6 5.8l1.3 1.1" />
    </svg>
  )
}

// QUALITY — a circle with a horizontal tick inside
export function IconQuality({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <circle cx="8" cy="8" r="6" />
      <path d="M5.2 8h5.6" />
    </svg>
  )
}

// CONTEXT — concentric circles (a target)
export function IconContext({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <circle cx="8" cy="8" r="6" />
      <circle cx="8" cy="8" r="3" />
      <circle cx="8" cy="8" r="0.4" fill="currentColor" stroke="none" />
    </svg>
  )
}

// PATHWAY — three nodes connected by two lines
export function IconPathway({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <circle cx="3" cy="12" r="1.6" />
      <circle cx="8" cy="4" r="1.6" />
      <circle cx="13" cy="12" r="1.6" />
      <path d="M4.3 10.8 6.8 5.4M9.2 5.4l2.5 5.4" />
    </svg>
  )
}

// RWR — a central node with four short radiating lines
export function IconRWR({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <circle cx="8" cy="8" r="2" />
      <path d="M8 2.5v2M8 11.5v2M2.5 8h2M11.5 8h2" />
    </svg>
  )
}

export const METRIC_ICONS: Record<string, (p: IconProps) => JSX.Element> = {
  rna: IconRNA,
  protein: IconProtein,
  quality: IconQuality,
  context: IconContext,
  pathway: IconPathway,
  rwr: IconRWR,
}
