import InstrumentReadout from './InstrumentReadout'
import { getScorePct } from '../utils/resultFields'

interface Props {
  result: any
  onCellLineClick: (cvcl: string) => void
}

// GRID view — corrected direction #2: a 96-well microplate, not an
// edge-to-edge card panel (that was the prior task's Part 4; this
// replaces it for GRID specifically — LIST and COMPACT are untouched).
// Each well is a genuine circle (aspect-square + rounded-full, not a
// rounded rectangle), holding exactly three things per the spec: the
// rank (small, top-right corner), the cell line name (centred, truncated
// to keep clear of the circle's curve), and the Fit Score numeral in
// Part 2's instrument-readout styling.
//
// The well's BORDER carries the hard-binary top-result signal (retargeted
// from FitRing's stroke, same `fitring-fill` mechanism/CSS rule — see
// index.css) — accent for rank 1, muted-state otherwise, full accent
// restored on hover/focus of that specific well. Because the well itself
// is the interactive element (not a separate ancestor wrapping a nested
// coloured node, unlike FitRing/ResultCard), it relies on the SELF-hover
// form of that rule (`.fitring-fill:hover`), not the ancestor form.
//
// diseaseFilter/lineageFilter/gene_class/gene_role are deliberately NOT
// shown here — this task's well spec lists exactly three contents (rank,
// name, Fit Score), and a well this small has no real room for a fourth.
// LIST and COMPACT still carry the full GENE CLASS/GENE ROLE/CONTEXT n/a
// treatment; clicking a well opens the same cell-line detail panel
// (SlideOver) as every other view for that deeper information.
export default function ResultCardGrid({ result, onCellLineClick }: Props) {
  const scorePct = getScorePct(result)
  const pct = Math.round(scorePct * 100)
  const isTop = result.rank === 1

  return (
    <button
      onClick={() => onCellLineClick(result.cellosaurus_id)}
      className="fitring-fill w-full aspect-square rounded-full flex flex-col items-center justify-center relative"
      style={{
        background: 'var(--bg-card)',
        border: `2px solid ${isTop ? 'var(--accent)' : 'var(--muted-state)'}`,
        transition: 'border-color 200ms ease',
      }}
      title={`${result.official_name} — rank ${result.rank}`}
    >
      <span
        className="absolute font-mono"
        style={{ top: '14%', right: '16%', fontSize: 9, color: 'var(--text-body)', opacity: 0.6 }}
      >
        {String(result.rank).padStart(2, '0')}
      </span>

      <span
        className="truncate font-semibold px-1"
        style={{ fontSize: 10, color: 'var(--text-heading)', maxWidth: '64%', textAlign: 'center', marginBottom: 4 }}
      >
        {result.official_name}
      </span>

      <InstrumentReadout value={`${pct}%`} color="var(--text-heading)" size="sm" />
    </button>
  )
}
