// Flat circular progress ring for the Fit Score. No glow, no blur, no
// gradient fill, no shadow: a plain track + fill arc, both flat strokes.
// The centre numeral reads as a confident, oversized instrument readout —
// deliberately the largest single number on a result card.
//
// `dim` (Part 5's hard binary contrast device): the single top-ranked
// result keeps the ring's accent fill; every other result renders it in
// --muted-state instead — a real, meaningful "this is the strongest
// match" signal using this tool's own rank, not decoration. The fill
// circle carries the `fitring-fill` class specifically so a parent
// `.result-card-wrap:hover`/`:focus` rule (see index.css) can restore
// full accent color on hover/focus of that specific card, per the task's
// "full contrast returning on hover/focus" requirement — done in CSS, not
// per-row JS state, since :hover/:focus already scope correctly with no
// extra bookkeeping across a list of cards.

interface Props {
  /** 0-1 */
  score: number
  size?: number
  label?: string
  dim?: boolean
}

export default function FitRing({ score, size = 88, label = 'FIT SCORE', dim = false }: Props) {
  const pct = Math.round(Math.min(1, Math.max(0, score || 0)) * 100)
  const stroke = Math.max(5, Math.round(size * 0.065))
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const dash = (pct / 100) * c

  // Part 2's instrument-readout treatment: a fixed-width inset "LCD"
  // plate behind the numeral (var(--bg) — a real existing token, reads as
  // subtly recessed against the card's var(--bg-card) in both themes, not
  // a new colour), sized for 3 monospace digits regardless of whether pct
  // is actually 1, 2, or 3 digits, so the plate never shifts/resizes
  // between result cards.
  const numeralSize = size * 0.32
  const plateW = numeralSize * 0.62 * 3 + numeralSize * 0.4
  const plateH = numeralSize * 1.3

  return (
    <div
      className="flex flex-col items-center justify-center flex-shrink-0"
      style={{ width: size }}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
        <circle
          cx={size / 2} cy={size / 2} r={r}
          fill="none" stroke="var(--border)" strokeWidth={stroke}
        />
        <circle
          className="fitring-fill"
          cx={size / 2} cy={size / 2} r={r}
          fill="none" stroke={dim ? 'var(--muted-state)' : 'var(--accent)'} strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${c - dash}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{ transition: 'stroke-dasharray 0.5s ease, stroke 200ms ease' }}
        />
        <rect
          x={size / 2 - plateW / 2} y={size / 2 - plateH / 2}
          width={plateW} height={plateH} rx={3}
          fill="var(--bg)"
        />
        <text
          x="50%" y="50%"
          textAnchor="middle" dominantBaseline="central"
          fontFamily="'IBM Plex Mono', monospace"
          fontSize={numeralSize}
          fontWeight={700}
          letterSpacing={numeralSize * 0.06}
          fill="var(--text-heading)"
        >
          {pct}
        </text>
      </svg>
      <span className="text-[10px] uppercase tracking-[0.08em] text-cso-body mt-1.5">{label}</span>
    </div>
  )
}
