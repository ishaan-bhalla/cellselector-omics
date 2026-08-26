export const api = {
  health: () =>
    fetch('/health').then(r => r.json()),

  stats: () =>
    fetch('/stats').then(r => r.json()),

  searchGene: (q: string) =>
    fetch(`/genes/search?q=${encodeURIComponent(q)}`).then(r => r.json()),

  recommendClassical: (body: {
    gene: string
    disease_filter?: string
    lineage_filter?: string
    exclude_genes?: string[]
    top_n?: number
  }) =>
    fetch('/recommend/classical', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...body, use_learned_weights: true }),
    }).then(r => r.json()),

  recommendAgentic: (body: {
    gene: string
    disease_filter?: string
    exclude_genes?: string[]
    target_cellosaurus_id?: string
    top_n?: number
  }) =>
    fetch('/recommend/agentic', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...body, use_learned_weights: true, top_n: 1 }),
    }).then(r => r.json()),

  cellLine: (cvcl_id: string) =>
    fetch(`/cell-lines/${cvcl_id}`).then(r => r.json()),

  browseCellLines: (params: { search?: string; limit?: number; offset?: number } = {}) => {
    const q = new URLSearchParams()
    if (params.search)             q.append('search', params.search)
    if (params.limit !== undefined) q.append('limit',  String(params.limit))
    if (params.offset !== undefined) q.append('offset', String(params.offset))
    const qs = q.toString()
    return fetch(`/cell-lines${qs ? '?' + qs : ''}`).then(r => r.json())
  },
}
