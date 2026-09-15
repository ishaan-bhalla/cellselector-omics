import { describeWeights, VALIDATION_SET_SIZE } from '../utils/weightExplanation'

// The content rendered inside HoverPopover, anchored to each card's Fit
// Score element (Item 2 — replaces the old permanent "How Fit Score is
// computed" panel). Leads with the REAL per-gene weight percentages for
// THIS card's query (from weights_used, not generic/static text), then a
// short methodology note beneath.
interface Props {
  /** The gene(s) this card's score is actually about, in query order. */
  genes: string[]
  /** allResults.weights_used — a flat dict for a single-gene query, or
   *  {gene: {...weights}} for a multi-gene query. */
  weightsUsed: any
  isMultiGene: boolean
  geneClass?: string
}

export default function FitScoreExplanation({ genes, weightsUsed, isMultiGene, geneClass }: Props) {
  return (
    <>
      {isMultiGene ? (
        <div className="space-y-1">
          {genes.map(g => (
            <p key={g}>
              <strong className="text-[var(--text-heading)]">{g}</strong>:{' '}
              {describeWeights(weightsUsed?.[g]) || 'weights unavailable'}
            </p>
          ))}
        </div>
      ) : (
        <p>
          Weights actually applied to{' '}
          <strong className="text-[var(--text-heading)]">{genes[0]}</strong>
          {geneClass ? `, a ${geneClass.replace(/_/g, ' ')} gene` : ''}:{' '}
          {describeWeights(weightsUsed) || 'weights unavailable'}.
        </p>
      )}
      <p className="mt-2 text-[10px]" style={{ opacity: 0.85 }}>
        Weighting is tuned per gene class, learned by maximising Mean
        Reciprocal Rank against a {VALIDATION_SET_SIZE}-gene validated set.
        GEO expression adds a separate ±10% confirmatory bonus, not
        included above. Pathway-coherence scoring was tested and found not
        to improve ranking accuracy, so it isn't part of the active
        weighting.
      </p>
    </>
  )
}
