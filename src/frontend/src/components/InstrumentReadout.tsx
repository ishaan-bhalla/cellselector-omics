// Shared "digital instrument readout" numeral treatment (Part 2) — used
// wherever a Fit Score numeral appears as plain HTML text rather than SVG
// (FitRing's own centre numeral stays SVG <text>, styled the same way
// directly in FitRing.tsx; this component is for ResultCardCompact's
// fit-% and the microplate well's numeral).
//
// Deliberately NOT a literal seven-segment digital font — that reads as a
// "digital clock" cliché. The instrument feeling instead comes from:
//   - monospace (IBM Plex Mono, already loaded) at a FIXED width, so a
//     1-, 2-, or 3-digit value never shifts the surrounding layout
//   - a slight letter-spacing increase
//   - a faint inset "LCD panel" plate behind the numeral — background:
//     var(--bg), which is a real, already-existing token, not a new
//     colour. --bg reads as subtly recessed against --bg-card in BOTH
//     themes by construction (page bg vs card bg were designed as two
//     close-but-distinct tones), so this achieves the recessed-panel look
//     with zero new colours, exactly as instructed.
interface Props {
  value: string
  /** Text (and, if fillMarker, stroke/border) colour — callers decide
   *  whether this element carries the hard-binary top-result signal. */
  color: string
  /** Adds the `fitring-fill` class so this element participates in the
   *  shared hover/focus-restore mechanism (see index.css) — only pass
   *  this when `color` is itself the accent/muted-state binary. */
  fillMarker?: boolean
  size?: 'sm' | 'md'
  className?: string
}

export default function InstrumentReadout({ value, color, fillMarker = false, size = 'md', className = '' }: Props) {
  const fontSize = size === 'sm' ? 11 : 14
  return (
    <span
      className={`${fillMarker ? 'fitring-fill ' : ''}inline-block text-center font-mono font-semibold ${className}`}
      style={{
        color,
        fontSize,
        letterSpacing: '0.06em',
        background: 'var(--bg)',
        borderRadius: 3,
        padding: size === 'sm' ? '2px 4px' : '3px 6px',
        minWidth: size === 'sm' ? 34 : 46,
      }}
    >
      {value}
    </span>
  )
}
