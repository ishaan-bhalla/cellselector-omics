// Shared with Search.tsx's old permanent "How Fit Score is computed"
// panel (now removed — see Item 2 of the UI/UX fixes task; this content
// moved to a per-card hover tooltip anchored to the Fit Score element
// itself, via components/FitScoreTooltip.tsx) and reused there so the
// weight descriptions can't drift between the two.
//
// Deliberately does NOT include "pathway": pathway-coherence scoring
// (KEGG pathway-neighbor co-expression) was tested via four separate
// aggregation methods and found not to improve ranking accuracy
// (post-translational activation mechanisms aren't visible to
// transcriptional co-expression scoring) — see the methodology note in
// FitScoreTooltip instead of listing it as an active weighted dimension.
// A weights_used dict CAN still carry a "pathway" key at 0.0 for some
// gene classes; omitting it from this table (rather than rendering "(0%)")
// is deliberate, not a bug.
export const WEIGHT_COMPONENT_INFO: Record<string, { label: string; description: string }> = {
  rna:         { label: 'RNA Expression',        description: 'transcript abundance across HPA and DepMap' },
  protein:     { label: 'Protein',                description: 'protein abundance from CCLE proteomics' },
  quality:     { label: 'Data Quality',           description: 'cross-source agreement and data completeness' },
  context:     { label: 'Context',                description: 'disease/tissue match to your search filter' },
  mutation:    { label: 'Mutation Impact',        description: 'damaging-variant status, the primary signal for loss-of-function genes' },
  copy_number: { label: 'Copy Number',            description: 'amplification status, for amplification-driven oncogenes' },
  rwr:         { label: 'Graph Centrality (RWR)', description: 'random-walk-with-restart network proximity across the gene/pathway/cell-line knowledge graph' },
}
export const WEIGHT_COMPONENT_ORDER = ['rna', 'protein', 'quality', 'context', 'mutation', 'copy_number', 'rwr']

// Active components for one gene's weights dict, e.g. "RNA Expression
// (46%), Protein (8%), ..." — only components actually present with a
// positive weight, so this is accurate for whichever gene class produced
// `w` (loss-of-function's mutation-primary vector has no rna/protein/
// quality/context weight worth mentioning at the same scale but still
// carries them at small values; amplification-driven genes add
// copy_number; every class now carries rwr).
export function describeWeights(w: Record<string, number> | undefined): string {
  if (!w) return ''
  return WEIGHT_COMPONENT_ORDER
    .filter(k => (w[k] ?? 0) > 0)
    .map(k => `${WEIGHT_COMPONENT_INFO[k].label} (${Math.round(w[k] * 100)}%)`)
    .join(', ')
}

// models.classical.weights_learned.VALIDATION_SET's length, confirmed
// directly against both the local repo and the deployed VM (44, not an
// older hardcoded "25" — stale since the CIViC-sourced expansion). Not
// read dynamically from /stats: that endpoint's validation_genes field
// exists but is sourced from outputs/model_evaluation.json, a frozen
// snapshot from BEFORE the 44-gene expansion (still reports 25) —
// regenerating that evaluation artifact is a separate, much larger task.
// Hardcoding here is deliberate, not an oversight; update this if
// VALIDATION_SET's size changes again.
export const VALIDATION_SET_SIZE = 44
