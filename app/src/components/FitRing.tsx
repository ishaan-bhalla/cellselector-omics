// Flat circular progress ring for the Fit Score — see the task's Part 2
// spec. No glow, no blur, no gradient fill, no shadow: a plain track +
// fill arc, both flat strokes.

interface Props {
  /** 0-1 */
  score: number
  size?: number
  label?: string
}

export default function FitRing({ score, size = 76, label = 'FIT SCORE' }: Props) {
  const pct = Math.round(Math.min(1, Math.max(0, score || 0)) * 100)
  const stroke = 6
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const dash = (pct / 100) * c

  return (
    <div
      className="flex flex-col items-center justify-center flex-shrink-0"
      style={{ width: size }}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <circle
          cx={size / 2} cy={size / 2} r={r}
          fill="none" stroke="#E5E3DD" strokeWidth={stroke}
        />
        <circle
          cx={size / 2} cy={size / 2} r={r}
          fill="none" stroke="#0F766E" strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${c - dash}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{ transition: 'stroke-dasharray 0.4s ease' }}
        />
        <text
          x="50%" y="50%"
          textAnchor="middle" dominantBaseline="central"
          fontFamily="'IBM Plex Mono', monospace"
          fontSize={size * 0.26}
          fontWeight={600}
          fill="#1A1A1A"
        >
          {pct}
        </text>
      </svg>
      <span className="text-[10px] uppercase tracking-[0.08em] text-cso-body mt-1">{label}</span>
    </div>
  )
}
