import { useState } from 'react'
import { METRIC_ICONS } from './icons/MetricIcons'
import { METRIC_INFO } from './MetricRow'
import InstrumentReadout from './InstrumentReadout'
import FitScoreExplanation from './FitScoreExplanation'
import { getScorePct, hasContextFilter as computeHasContextFilter, isMultiGeneResult } from '../utils/resultFields'

interface Props {
  result: any
  gene: string
  additionalGenes?: string[]
  diseaseFilter?: string
  weightsUsed?: any
  onCellLineClick: (cvcl: string) => void
}

// COMPACT view — a dense single-line-per-result row for scanning many
// results fast (see ViewModeToggle / Part 3): rank, name, fit score, gene
// class, and exactly two metrics. RNA and CONTEXT were chosen for those
// two specifically (not an arbitrary pick) — RNA is the one metric every
// single-gene result always has a real number for, and CONTEXT is the one
// most likely to be "n/a" (Part 1, PROBLEM B), so this view exercises
// that exact rule too rather than only ever showing populated metrics.
// Both keep their hover-explanation tooltip; gene class keeps its own —
// condensed onto one line, but the Part 1 labelling fix isn't dropped
// here, just laid out differently than LIST/GRID's two-line rows.
function CompactMetric({ metric, value, tooltip }: { metric: 'rna' | 'context'; value: number | null; tooltip?: string }) {
  const info = METRIC_INFO[metric]
  const Icon = METRIC_ICONS[metric]
  return (
    <span className="flex items-center gap-1 flex-shrink-0" title={tooltip ?? info.description}>
      <span className="text-cso-body"><Icon /></span>
      <span className="font-mono text-xs text-cso-heading w-9">
        {value === null ? 'n/a' : value.toFixed(2)}
      </span>
    </span>
  )
}

export default function ResultCardCompact({ result, gene, additionalGenes, diseaseFilter, weightsUsed, onCellLineClick }: Props) {
  const isMultiGene = isMultiGeneResult(result)
  const scorePct = getScorePct(result)
  const hasFilter = computeHasContextFilter(diseaseFilter)
  const pct = Math.round(scorePct * 100)
  const isTop = result.rank === 1
  // Item 2: same reasoning as ResultCardGrid — the whole row is already
  // one <button>, so the Fit Score hover explanation can't be a nested
  // HoverPopover (invalid interactive-in-interactive nesting); its state
  // and markup are inlined here instead.
  const [hovered, setHovered] = useState(false)

  return (
    <button
      onClick={() => onCellLineClick(result.cellosaurus_id)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocus={() => setHovered(true)}
      onBlur={() => setHovered(false)}
      className="result-card-wrap w-full flex items-center gap-4 px-4 py-2.5 text-left hover:bg-cso-bg transition-colors relative"
      style={{ borderBottom: '1px solid var(--border)' }}
    >
      <span className="font-mono text-xs text-cso-body w-6 flex-shrink-0" style={{ opacity: 0.6 }}>
        {String(result.rank).padStart(2, '0')}
      </span>

      <InstrumentReadout
        value={`${pct}%`}
        color={isTop ? 'var(--accent)' : 'var(--muted-state)'}
        fillMarker
        size="sm"
        className="flex-shrink-0"
      />

      {hovered && (
        <div
          role="tooltip"
          className="absolute z-40 bg-cso-card border border-[var(--border)] rounded p-3 text-xs text-[var(--text-body)] leading-relaxed text-left"
          style={{ width: 280, left: 40, top: '100%', marginTop: 4, pointerEvents: 'none' }}
        >
          <FitScoreExplanation
            genes={[gene, ...(additionalGenes ?? [])]}
            weightsUsed={weightsUsed}
            isMultiGene={isMultiGene}
            geneClass={result.gene_class}
          />
        </div>
      )}

      <span className="flex-1 min-w-0 truncate text-sm font-semibold" style={{ color: 'var(--text-heading)' }}>
        {result.official_name}
      </span>

      {!isMultiGene && result.gene_class && (
        <span
          className="text-[10px] uppercase tracking-[0.06em] text-cso-body flex-shrink-0 hidden sm:inline cursor-help"
          title="Determines which evidence types are weighted most heavily for this gene."
        >
          {(result.gene_class as string).replace(/_/g, '-')}
        </span>
      )}

      {!isMultiGene && (
        <span className="hidden md:flex items-center gap-3 flex-shrink-0">
          <CompactMetric metric="rna" value={result.rna_score ?? 0} />
          <CompactMetric
            metric="context"
            value={hasFilter ? (result.context_score ?? 0) : null}
            tooltip={hasFilter ? undefined : 'No disease or tissue filter was applied to this search'}
          />
        </span>
      )}
    </button>
  )
}
