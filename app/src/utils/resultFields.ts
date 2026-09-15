// Shared derived-data logic for every result-card layout (LIST/GRID/
// COMPACT — see ViewModeToggle). Centralised so the CONTEXT n/a rule and
// the multi-gene/score-percent logic can't drift between variants; each
// variant renders this data differently, but never recomputes it
// differently.

export function isMultiGeneResult(result: any): boolean {
  return result.per_gene_percentiles != null
}

export function getScorePct(result: any): number {
  const isMulti = isMultiGeneResult(result)
  return (isMulti ? result.combined_score : result.final_score) ?? 0
}

// CONTEXT is "n/a", not 0.00, when no disease/tissue filter was applied —
// see Part 1 PROBLEM B of the original redesign task. Both filters are
// checked (either can produce a real context_score).
export function hasContextFilter(diseaseFilter?: string, lineageFilter?: string): boolean {
  return Boolean(diseaseFilter?.trim() || lineageFilter?.trim())
}

export function getSources(result: any): string[] {
  return [
    (result.hpa_score ?? 0) > 0 && 'HPA RNA',
    (result.depmap_score ?? 0) > 0 && 'DepMap',
    (result.geo_confirmation ?? 0) !== 0 && 'GEO',
    (result.protein_score ?? 0) > 0 && 'Proteomics',
  ].filter(Boolean) as string[]
}
