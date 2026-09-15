import FitRing from './FitRing'
import MetricRow from './MetricRow'
import LabelValueRow from './LabelValueRow'
import { getScorePct, getSources, hasContextFilter as computeHasContextFilter, isMultiGeneResult } from '../utils/resultFields'

interface Props {
  result: any
  diseaseFilter?: string
  lineageFilter?: string
  onCellLineClick: (cvcl: string) => void
}

// GRID view — a more compact per-card layout than LIST (see
// ViewModeToggle): still carries the Part 1 labelling fix (GENE CLASS /
// GENE ROLE, metric tooltips, CONTEXT n/a) in full, but drops the
// collapsible Alternatives / Score breakdown / AI Justification depth —
// click through to the cell line detail panel (same as LIST's name click)
// for that. Trimmed to 4 evidence metrics (RNA/PROTEIN/QUALITY/CONTEXT,
// dropping PATHWAY/RWR) to actually earn "compact," not just relabelled.
export default function ResultCardGrid({ result, diseaseFilter, lineageFilter, onCellLineClick }: Props) {
  const isMultiGene = isMultiGeneResult(result)
  const scorePct = getScorePct(result)
  const hasFilter = computeHasContextFilter(diseaseFilter, lineageFilter)
  const sources = getSources(result)
  const isTop = result.rank === 1

  return (
    <div className={`bg-cso-card border border-cso-border rounded p-4 ${isTop ? 'border-l-4 border-l-cso-teal' : ''}`}>
      <div className="flex items-start justify-between mb-3 gap-3">
        <div className="flex items-start gap-2.5 flex-1 min-w-0">
          <span
            className="font-mono leading-none flex-shrink-0"
            style={{ fontSize: '1.5rem', fontWeight: 300, color: 'var(--text-body)', opacity: 0.6 }}
          >
            {String(result.rank).padStart(2, '0')}
          </span>
          <div className="min-w-0 pt-0.5">
            <button
              onClick={() => onCellLineClick(result.cellosaurus_id)}
              className="hover:text-cso-teal transition-colors text-left truncate block w-full"
              style={{ color: 'var(--text-heading)', fontWeight: 700, fontSize: '1rem', lineHeight: 1.2 }}
            >
              {result.official_name}
            </button>
            <div className="text-cso-body font-mono text-[11px] mt-0.5">{result.cellosaurus_id}</div>
          </div>
        </div>
        <FitRing score={scorePct} label={isMultiGene ? 'COMBINED' : 'FIT'} size={56} />
      </div>

      {isMultiGene ? (
        <div className="text-xs text-cso-body font-mono mb-2">
          {Object.entries(result.per_gene_percentiles as Record<string, number>)
            .map(([g, pct]) => `${g}: ${Math.round(pct * 100)}%ile`)
            .join(', ')}
        </div>
      ) : (
        <>
          {(result.gene_class || result.gene_role) && (
            <div className="mb-2">
              {result.gene_class && (
                <LabelValueRow
                  label="Class"
                  value={(result.gene_class as string).replace(/_/g, '-')}
                  explanation="Determines which evidence types are weighted most heavily for this gene."
                />
              )}
              {result.gene_role && (
                <LabelValueRow
                  label="Role"
                  value={result.gene_role}
                  explanation="The gene's biological function, for context."
                />
              )}
            </div>
          )}

          <div className="mb-2">
            <MetricRow metric="rna"     value={result.rna_score ?? 0} />
            <MetricRow metric="protein" value={result.protein_score ?? 0} />
            <MetricRow metric="quality" value={result.quality_score ?? 0} />
            <MetricRow
              metric="context"
              value={hasFilter ? (result.context_score ?? 0) : null}
              tooltip={hasFilter ? undefined : 'No disease or tissue filter was applied to this search'}
            />
          </div>

          {sources.length > 0 && (
            <div className="flex flex-wrap gap-1 mb-1">
              {sources.map(s => (
                <span key={s} className="text-[10px] border border-cso-border text-cso-body px-1.5 py-0.5 rounded-full">
                  {s}
                </span>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
