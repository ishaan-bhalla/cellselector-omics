import { METRIC_ICONS } from './icons/MetricIcons'
import { METRIC_INFO } from './MetricRow'

// Item 3 finding: GRID's microplate wells show zero individual metrics
// (by design — a well has room for exactly rank/name/Fit Score, see
// ResultCardGrid's own docstring), and clicking through to the cell-line
// detail panel (SlideOver) does NOT cover this gap either — it shows
// disease/lineage/data-coverage/genomic-features, not the RNA/PROTEIN/
// QUALITY/CONTEXT/PATHWAY/RWR breakdown with descriptions. Rather than
// leave that as an unaddressed gap, this reuses the SAME hover popover
// Item 2 already added to each well (showing the Fit Score weight
// explanation) to also list the metrics compactly underneath — each
// still carries its own title-attribute explanation from METRIC_INFO,
// same as MetricRow's LIST/GRID... er, LIST/COMPACT tooltips, just laid
// out as a dense label:value list rather than full bars (no room for
// bars at this scale).
interface Props {
  result: any
  hasContextFilter: boolean
}

const GRID_METRICS: Array<keyof typeof METRIC_INFO> = ['rna', 'protein', 'quality', 'context', 'pathway', 'rwr']
const RESULT_FIELD: Record<string, string> = {
  rna: 'rna_score', protein: 'protein_score', quality: 'quality_score',
  context: 'context_score', pathway: 'pathway_activity_score', rwr: 'rwr_score',
}

export default function CompactMetricList({ result, hasContextFilter }: Props) {
  return (
    <div className="mt-2 pt-2 grid grid-cols-2 gap-x-3 gap-y-1" style={{ borderTop: '1px solid var(--border)' }}>
      {GRID_METRICS.map(metric => {
        const info = METRIC_INFO[metric]
        const Icon = METRIC_ICONS[metric]
        const raw = metric === 'context' && !hasContextFilter
          ? null
          : (result[RESULT_FIELD[metric]] ?? 0)
        const tooltip = metric === 'context' && !hasContextFilter
          ? 'No disease or tissue filter was applied to this search'
          : info.description
        return (
          <span key={metric} className="flex items-center gap-1" title={tooltip}>
            <span className="text-cso-body flex-shrink-0"><Icon /></span>
            <span className="text-[9px] uppercase tracking-[0.06em] text-cso-body">{info.label}</span>
            <span className="font-mono text-[10px] ml-auto" style={{ color: 'var(--text-heading)' }}>
              {raw === null ? 'n/a' : Number(raw).toFixed(2)}
            </span>
          </span>
        )
      })}
    </div>
  )
}
