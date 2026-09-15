import { useState } from 'react'
import InstrumentReadout from './InstrumentReadout'
import FitScoreExplanation from './FitScoreExplanation'
import CompactMetricList from './CompactMetricList'
import { getScorePct, hasContextFilter as computeHasContextFilter } from '../utils/resultFields'

interface Props {
  result: any
  gene: string
  additionalGenes?: string[]
  diseaseFilter?: string
  weightsUsed?: any
  isMultiGene: boolean
  onCellLineClick: (cvcl: string) => void
}

// GRID view — a 96-well microplate. Each well is a genuine circle
// (aspect-square + rounded-full, not a rounded rectangle), holding
// exactly three things per the spec: the rank (small, top-right corner),
// the cell line name (centred, truncated to keep clear of the circle's
// curve), and the Fit Score numeral in the instrument-readout styling.
//
// The well's BORDER carries the hard-binary top-result signal (retargeted
// from FitRing's stroke, same `fitring-fill` mechanism/CSS rule — see
// index.css) — accent for rank 1, muted-state otherwise, full accent
// restored on hover/focus of that specific well. Because the well itself
// is the interactive element (not a separate ancestor wrapping a nested
// coloured node, unlike FitRing/ResultCard), it relies on the SELF-hover
// form of that rule (`.fitring-fill:hover`), not the ancestor form.
//
// Item 2: the well itself is ALREADY the one clickable element (opens the
// detail panel), so the Fit Score hover explanation can't be a nested
// HoverPopover (a focusable div inside a <button> is invalid interactive
// nesting) — its hover/focus state and popover markup are inlined here
// directly on the same button instead, same visual result.
//
// gene_class/gene_role are deliberately NOT shown as VISIBLE well content
// — this task's well spec lists exactly three always-visible contents
// (rank, name, Fit Score), and a well this small has no real room for a
// fourth. LIST and COMPACT still carry the full GENE CLASS/GENE ROLE
// treatment; clicking a well opens the same cell-line detail panel
// (SlideOver) as every other view for that deeper information.
//
// Item 3 finding: GRID showed ZERO individual metrics (RNA/PROTEIN/
// QUALITY/CONTEXT/PATHWAY/RWR) — a real gap, since clicking through to
// SlideOver doesn't cover it either (that panel shows different
// information). Closed by reusing this same hover popover to also list
// them compactly (CompactMetricList) beneath the weight breakdown —
// still per-metric hover explanations (title attributes from the same
// METRIC_INFO), just laid out densely rather than as full bars.
export default function ResultCardGrid({ result, gene, additionalGenes, diseaseFilter, weightsUsed, isMultiGene, onCellLineClick }: Props) {
  const scorePct = getScorePct(result)
  const pct = Math.round(scorePct * 100)
  const isTop = result.rank === 1
  const hasFilter = computeHasContextFilter(diseaseFilter)
  const [hovered, setHovered] = useState(false)

  return (
    <button
      onClick={() => onCellLineClick(result.cellosaurus_id)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocus={() => setHovered(true)}
      onBlur={() => setHovered(false)}
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

      {hovered && (
        <div
          role="tooltip"
          className="absolute z-40 bg-cso-card border border-[var(--border)] rounded p-3 text-xs text-[var(--text-body)] leading-relaxed text-left"
          style={{
            width: 280, left: '50%', bottom: '100%', marginBottom: 8,
            transform: 'translateX(-50%)', pointerEvents: 'none',
          }}
        >
          <FitScoreExplanation
            genes={[gene, ...(additionalGenes ?? [])]}
            weightsUsed={weightsUsed}
            isMultiGene={isMultiGene}
            geneClass={result.gene_class}
          />
          {!isMultiGene && <CompactMetricList result={result} hasContextFilter={hasFilter} />}
        </div>
      )}
    </button>
  )
}
