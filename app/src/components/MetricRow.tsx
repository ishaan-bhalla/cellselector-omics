import { METRIC_ICONS } from './icons/MetricIcons'

export const METRIC_INFO: Record<string, { label: string; description: string }> = {
  rna:     { label: 'RNA',     description: 'Expression level across HPA and DepMap' },
  protein: { label: 'PROTEIN', description: 'Protein abundance from CCLE proteomics' },
  quality: { label: 'QUALITY', description: 'Cross-source agreement and data completeness' },
  context: { label: 'CONTEXT', description: 'Match to your disease or tissue filter' },
  pathway: { label: 'PATHWAY', description: 'Pathway-neighbour genes also expressed here' },
  rwr:     { label: 'RWR',     description: 'Network proximity to the target gene in the knowledge graph' },
}

function barColor(value: number): string {
  if (value >= 0.66) return 'var(--accent)'
  if (value >= 0.33) return 'var(--accent-amber)'
  return 'var(--muted-state)'
}

interface Props {
  metric: keyof typeof METRIC_INFO
  /** null/undefined renders as "n/a" with no bar */
  value: number | null | undefined
  /** Overrides the default hover text (used for CONTEXT's "no filter applied" case) */
  tooltip?: string
}

export default function MetricRow({ metric, value, tooltip }: Props) {
  const info = METRIC_INFO[metric]
  const Icon = METRIC_ICONS[metric]
  const isNA = value === null || value === undefined
  const clamped = isNA ? 0 : Math.min(1, Math.max(0, value))
  const pct = Math.round(clamped * 100)

  return (
    <div
      className="flex items-center gap-2.5 py-1"
      title={tooltip ?? info.description}
    >
      <span className="text-cso-body flex-shrink-0">
        <Icon />
      </span>
      <span className="text-[11px] uppercase tracking-[0.08em] text-cso-body w-16 flex-shrink-0">
        {info.label}
      </span>
      {isNA ? (
        <>
          <div className="flex-1" />
          <span className="font-mono text-xs text-cso-muted w-12 text-right flex-shrink-0">n/a</span>
        </>
      ) : (
        <>
          <div className="flex-1 h-1 rounded-sm overflow-hidden" style={{ background: 'var(--border)' }}>
            <div
              style={{ width: `${pct}%`, background: barColor(clamped), height: '100%', transition: 'width 0.4s ease' }}
            />
          </div>
          <span className="font-mono text-xs text-cso-heading w-12 text-right flex-shrink-0">
            {clamped.toFixed(2)}
          </span>
        </>
      )}
    </div>
  )
}
