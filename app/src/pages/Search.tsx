import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import ResultCard from '../components/ResultCard'
import SlideOver from '../components/SlideOver'

const LOADING_LINES = [
  'Resolving gene symbol',
  'Computing RNA expression scores',
  'Applying protein expression weights',
  'Running GEO cross-validation',
  'Ranking 2,076 cell lines',
  'Computing similarity alternatives',
  'Analysis complete',
]

// models.classical.weights_learned.VALIDATION_SET's length, confirmed
// directly against both the local repo and the deployed VM (44, not the
// panel's old hardcoded "25" — stale since the CIViC-sourced expansion).
// Not read dynamically from /stats: that endpoint's validation_genes field
// exists but is sourced from outputs/model_evaluation.json, a frozen
// snapshot from BEFORE the 44-gene expansion (still reports 25) —
// regenerating that evaluation artifact is a separate, much larger task,
// not part of this text-accuracy fix. Hardcoding here is deliberate, not
// an oversight; update this if VALIDATION_SET's size changes again.
const VALIDATION_SET_SIZE = 44

// Safety cap on multi-gene search size, mirroring api/models.py's
// MAX_ADDITIONAL_GENES. NOT a permanent feature limit — the parallelized
// multi-gene rank() fetch (models.classical.multi_gene_ranker) was only
// load-tested up to 2 total genes; that test showed the server's memory
// spiking to ~57% of the VM's total before releasing. Beyond that is
// unverified, so the backend rejects (422) anything over this cap and the
// UI hides "+ Add another gene" at the same point rather than letting a
// user hit that rejection. Keep this in sync with the backend value —
// raise only after isolated, memory-capped testing confirms headroom.
const MAX_ADDITIONAL_GENES = 1

// Active Fit Score weight components this panel can describe — deliberately
// does NOT include "pathway": pathway-coherence scoring (KEGG
// pathway-neighbor co-expression) was tested via four separate aggregation
// methods and found not to improve ranking accuracy (post-translational
// activation mechanisms aren't visible to transcriptional co-expression
// scoring) — see the methodology note rendered below instead of listing it
// as an active weighted dimension. A weights_used dict CAN still carry a
// "pathway" key at 0.0 for some gene classes; omitting it from this table
// (rather than rendering "(0%)") is deliberate, not a bug.
const WEIGHT_COMPONENT_INFO: Record<string, { label: string; description: string }> = {
  rna:         { label: 'RNA Expression',        description: 'transcript abundance across HPA and DepMap' },
  protein:     { label: 'Protein',                description: 'protein abundance from CCLE proteomics' },
  quality:     { label: 'Data Quality',           description: 'cross-source agreement and data completeness' },
  context:     { label: 'Context',                description: 'disease/tissue match to your search filter' },
  mutation:    { label: 'Mutation Impact',        description: 'damaging-variant status, the primary signal for loss-of-function genes' },
  copy_number: { label: 'Copy Number',            description: 'amplification status, for amplification-driven oncogenes' },
  rwr:         { label: 'Graph Centrality (RWR)', description: 'random-walk-with-restart network proximity across the gene/pathway/cell-line knowledge graph' },
}
const WEIGHT_COMPONENT_ORDER = ['rna', 'protein', 'quality', 'context', 'mutation', 'copy_number', 'rwr']

// Active components for one gene's weights dict, e.g. "RNA Expression
// (46%), Protein (8%), ..." — only components actually present with a
// positive weight, so this is accurate for whichever gene class produced
// `w` (loss-of-function's mutation-primary vector has no rna/protein/
// quality/context weight worth mentioning at the same scale but still
// carries them at small values; amplification-driven genes add
// copy_number; every class now carries rwr).
function describeWeights(w: Record<string, number> | undefined): string {
  if (!w) return ''
  return WEIGHT_COMPONENT_ORDER
    .filter(k => (w[k] ?? 0) > 0)
    .map(k => `${WEIGHT_COMPONENT_INFO[k].label} (${Math.round(w[k] * 100)}%)`)
    .join(', ')
}

// Shared gene autocomplete input — used for BOTH the primary gene input and
// any additional-gene input(s) added via "+ Add another gene" (see Search()
// below), rather than duplicating the dropdown/filtering logic per input.
// Fully controlled (value/onChange owned by the caller) so the primary and
// additional inputs can have different clear-after-select behavior without
// this component needing to know which one it is.
function GeneAutocompleteInput({
  value,
  onChange,
  onSelect,
  allGenes,
  excludeFromSuggestions = [],
  placeholder,
  autoFocus,
}: {
  value: string
  onChange: (v: string) => void
  onSelect: (g: string) => void
  allGenes: string[]
  excludeFromSuggestions?: string[]
  placeholder?: string
  autoFocus?: boolean
}) {
  const [showDropdown, setShowDropdown] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!showDropdown) return
    const handler = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setShowDropdown(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showDropdown])

  const suggestions = useMemo(() => {
    const q = value.trim().toUpperCase()
    if (!q) return []
    return allGenes
      .filter(g => g.startsWith(q) && !excludeFromSuggestions.includes(g))
      .slice(0, 10)
  }, [value, allGenes, excludeFromSuggestions])

  return (
    <div className="relative" ref={wrapRef}>
      <input
        type="text"
        value={value}
        onChange={e => { onChange(e.target.value); setShowDropdown(true) }}
        onFocus={() => value.trim() && setShowDropdown(true)}
        placeholder={placeholder}
        autoFocus={autoFocus}
        autoComplete="off"
        className="w-full bg-cso-card border border-[var(--border)] text-[var(--text-heading)] font-mono text-lg px-4 py-3 rounded focus:outline-none focus:border-[var(--accent)] transition-colors placeholder-[var(--muted-state)]"
      />
      {showDropdown && suggestions.length > 0 && (
        <div className="absolute left-0 right-0 z-20 mt-1 max-h-64 overflow-y-auto bg-cso-card border border-[var(--border)] rounded">
          {suggestions.map(g => (
            <button
              key={g}
              type="button"
              onClick={() => { onSelect(g); setShowDropdown(false) }}
              className="w-full text-left px-4 py-2 font-mono text-sm text-[var(--text-heading)] hover:bg-[var(--bg)] transition-colors"
            >
              {g}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Search() {
  const [gene, setGene] = useState('')
  // Per-gene stats (found/sources/cell-line count) for the gene actually
  // SELECTED from the dropdown — no longer fetched per keystroke, so
  // there's no async request in flight during typing to race against.
  const [geneInfo, setGeneInfo] = useState<any>(null)
  const [geneLoading, setGeneLoading] = useState(false)
  const [diseaseFilter, setDiseaseFilter] = useState('')
  const [lineageFilter, setLineageFilter] = useState('')
  const [excludeGenes, setExcludeGenes] = useState('')
  const [topN, setTopN] = useState(10)
  const [allResults, setAllResults] = useState<any>(null)
  const [pathwayResults, setPathwayResults] = useState<any[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadLine, setLoadLine] = useState(0)
  const [selectedCVCL, setSelectedCVCL] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Full gene list, fetched once on mount — see the useEffect below.
  // Client-side filtering of this replaces the old per-keystroke
  // /genes/search autocomplete entirely (eliminates both the backend load
  // and the out-of-order-response race condition class debugged tonight,
  // structurally — there's no per-keystroke fetch left to race).
  const [allGenes, setAllGenes] = useState<string[]>([])
  // Tracks which gene the in-flight one-time stats fetch (fired on
  // dropdown selection, see selectGene) is actually FOR — a minimal,
  // ref-based guard (not the AbortController machinery removed from the
  // old per-keystroke path) so that if a user selects a second gene
  // before the first stats fetch resolves, the stale response can't
  // silently overwrite the newer one. Deliberately kept minimal: nothing
  // to cancel, just "is this response still the one we care about".
  const selectedGeneRef = useRef('')
  // Additional genes for a combined multi-gene search (see handleSearch's
  // additional_genes wiring) — separate from `gene` (the primary), plus a
  // draft for whatever's currently being typed in the "add another gene"
  // box, which clears after each successful add (unlike the primary
  // input, which keeps showing the selected gene).
  const [additionalGenes, setAdditionalGenes] = useState<string[]>([])
  const [additionalGeneDraft, setAdditionalGeneDraft] = useState('')
  const [showAddGene, setShowAddGene] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const exportMenuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api.getAllGenes()
      .then(d => setAllGenes(d.genes ?? []))
      .catch(() => setAllGenes([]))
  }, [])

  const selectGene = async (g: string) => {
    setGene(g)
    selectedGeneRef.current = g
    setGeneInfo(null)
    setGeneLoading(true)
    try {
      const r = await api.searchGene(g)
      if (selectedGeneRef.current === g) setGeneInfo(r)
    } catch {
      if (selectedGeneRef.current === g) setGeneInfo(null)
    } finally {
      if (selectedGeneRef.current === g) setGeneLoading(false)
    }
  }

  const addAdditionalGene = (g: string) => {
    setAdditionalGeneDraft('')
    if (g === gene || additionalGenes.includes(g)) return
    // Defensive guard matching the cap enforced above (the add UI is
    // hidden once the cap is reached, so this shouldn't normally fire,
    // but keeps this function safe to call from anywhere).
    setAdditionalGenes(prev =>
      prev.length >= MAX_ADDITIONAL_GENES ? prev : [...prev, g]
    )
  }

  const removeAdditionalGene = (g: string) => {
    setAdditionalGenes(prev => prev.filter(x => x !== g))
  }

  useEffect(() => {
    if (!exportOpen) return
    const handler = (e: MouseEvent) => {
      if (exportMenuRef.current && !exportMenuRef.current.contains(e.target as Node)) {
        setExportOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [exportOpen])

  useEffect(() => {
    if (!loading) { setLoadLine(0); return }
    const id = setInterval(() => setLoadLine(l => Math.min(l + 1, LOADING_LINES.length - 1)), 650)
    return () => clearInterval(id)
  }, [loading])

  const handleSearch = async () => {
    const g = gene.trim().toUpperCase()
    if (!g) return

    const excludeList = excludeGenes
      ? excludeGenes.split(',').map(s => s.trim().toUpperCase()).filter(Boolean)
      : []
    if (excludeList.includes(g)) {
      setError(`Cannot search for ${g} and exclude it at the same time.`)
      return
    }

    setLoading(true); setAllResults(null); setPathwayResults(null); setError(null)
    try {
      const diseaseFilterVal = diseaseFilter.trim() || undefined
      // Pathway-connected recommendations are fetched alongside the main
      // search, not on a separate user action. A failure here (e.g. the
      // gene isn't yet ingested into the graph) shouldn't break the main
      // results, so it's caught independently rather than via the outer catch.
      // Deliberately still primary-gene-only (unaffected by additionalGenes)
      // — out of scope for this task.
      const [r, pw] = await Promise.all([
        api.recommendClassical({
          gene: g,
          // additionalGenes is always a real array (possibly empty) — sent
          // as-is, matching what additional_genes: list[str] =
          // Field(default_factory=list) on the backend expects. An empty
          // array here takes the EXACT SAME code path as before this
          // change (see api/main.py: `if body.additional_genes:` is False
          // for []), so a search with nothing added is unaffected.
          additional_genes: additionalGenes,
          disease_filter: diseaseFilterVal,
          lineage_filter: lineageFilter.trim() || undefined,
          exclude_genes: excludeList.length ? excludeList : undefined,
          // Was 50, matching the "Top" dropdown's max option (line ~231)
          // so it could resize the display client-side with no refetch.
          // Reduced to 20 (the dropdown's second-highest option) to cut
          // backend work — see the timing investigation report. Trade-off
          // accepted deliberately: selecting "Top 50" now shows only the
          // 20 fetched, a minor label/content mismatch, not a crash — the
          // dropdown itself was intentionally left at [5, 10, 20, 50].
          top_n: 20,
        }),
        api.cellLinesViaPathway(g, diseaseFilterVal, 5).catch(() => null),
      ])
      if (r.detail) throw new Error(r.detail)
      setAllResults(r)
      setPathwayResults(pw?.results ?? null)
    } catch (e: any) {
      setError(e?.message ?? 'Request failed. Is the API running on port 8001?')
    } finally {
      setLoading(false)
    }
  }

  const exportJSON = () => {
    if (!allResults) return
    const blob = new Blob([JSON.stringify(allResults, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `cellselector_${gene}_${new Date().toISOString().split('T')[0]}.json`
    a.click(); URL.revokeObjectURL(url)
  }

  const exportCSV = () => {
    if (!allResults?.results) return
    const headers = ['rank','cellosaurus_id','official_name','final_score','rna_score',
      'protein_score','quality_score','context_score','n_sources','gene_class','disease','lineage']
    const rows = (allResults.results as any[]).map((r: any) => headers.map(h => r[h] ?? '').join(','))
    const csv = [headers.join(','), ...rows].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `cellselector_${gene}_${new Date().toISOString().split('T')[0]}.csv`
    a.click(); URL.revokeObjectURL(url)
  }

  const exportPDF = async () => {
    if (!allResults?.session_id) {
      alert('No session available, run a search first')
      return
    }
    const response = await fetch(`/recommend/export/pdf?session_id=${allResults.session_id}`)
    if (!response.ok) {
      console.error('PDF export failed', response.status)
      return
    }
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `cellselector_${gene}_${new Date().toISOString().split('T')[0]}.pdf`
    a.click()
    URL.revokeObjectURL(url)
  }

  const displayedResults = allResults
    ? { ...allResults, results: (allResults.results as any[]).slice(0, topN) }
    : null

  // Actual weights the API used for this query (learned or fixed) — the
  // scoring panel reads real numbers from here rather than hardcoding them,
  // since learned weights (the default) don't match any fixed percentage.
  // For a multi-gene query, weights_used is {gene: {...weights}, ...} —
  // a different shape the single-gene panel below doesn't understand, so
  // it's gated off entirely for multi-gene rather than shown garbled.
  const w = allResults?.weights_used
  const isMultiGene = (allResults?.query?.additional_genes?.length ?? 0) > 0

  // geneInfo is now only ever populated by selectGene() for a gene already
  // confirmed present in allGenes — a "not found" state is structurally
  // unreachable through the dropdown, so there's no error branch to render
  // here any more (see STEP 3 of the client-side-autocomplete task).
  const sourcesFound = geneInfo?.sources
    ? Object.entries(geneInfo.sources as Record<string, boolean>)
        .filter(([, v]) => v).map(([k]) => k).join(' · ')
    : ''

  const inputCls = `w-full bg-cso-card border border-[var(--border)] text-[var(--text-heading)] px-4 py-2.5 rounded text-sm focus:outline-none focus:border-[var(--text-heading)] transition-colors placeholder-[var(--border)]`

  return (
    <div className="min-h-screen bg-cso-bg">
      {/* Search panel */}
      <div className="bg-cso-card border-b border-[var(--border)] pt-10">
        <div className="max-w-3xl mx-auto px-6 pb-8">
          <p className="text-[var(--text-body)] text-xs tracking-[0.2em] uppercase mb-2">Cell Line Recommender</p>
          <h1 className="text-[var(--text-heading)] text-3xl font-bold mb-8">Search Tool</h1>

          {/* Gene input — client-side-filtered dropdown via the shared
              GeneAutocompleteInput (also used below for additional genes).
              Zero network requests while typing; suggestions filtered
              instantly from the already-loaded full gene list. */}
          <div className="mb-5">
            <label className="text-[var(--text-body)] text-xs uppercase tracking-widest block mb-2">Gene Name</label>
            <div className="relative">
              <GeneAutocompleteInput
                value={gene}
                onChange={v => { setGene(v); setGeneInfo(null) }}
                onSelect={selectGene}
                allGenes={allGenes}
                excludeFromSuggestions={additionalGenes}
                placeholder="e.g. EGFR, BRCA1, KIT"
                autoFocus
              />
              {geneLoading && (
                <div className="absolute right-3.5 top-4">
                  <div className="w-4 h-4 border border-[var(--border)] border-t-[var(--text-heading)] rounded-full animate-spin" />
                </div>
              )}
            </div>
            {geneInfo && !geneLoading && (
              <div className="mt-2 text-xs font-mono text-[var(--accent)]">
                {`${geneInfo.gene ?? gene.toUpperCase()}, ${sourcesFound}, ${geneInfo.total_cell_lines_with_data?.toLocaleString()} cell lines`}
              </div>
            )}

            {/* Additional genes — combined multi-gene search. Removable
                chips match the "source chips" pill pattern already used in
                ResultCard, not a new visual style. */}
            {additionalGenes.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-3">
                {additionalGenes.map(g => (
                  <span
                    key={g}
                    className="inline-flex items-center gap-1.5 text-xs font-mono bg-[var(--bg)] text-[var(--text-heading)] px-2.5 py-1 rounded-full"
                  >
                    {g}
                    <button
                      type="button"
                      onClick={() => removeAdditionalGene(g)}
                      aria-label={`Remove ${g}`}
                      className="text-[var(--text-body)] hover:text-[var(--accent-amber)] transition-colors leading-none"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}

            {additionalGenes.length >= MAX_ADDITIONAL_GENES ? (
              // Cap reached — hide the add control entirely rather than a
              // disabled button, with a brief explanation so it's clear
              // this is a deliberate limit, not a missing feature. Mirrors
              // the backend's rejection message in api/models.py.
              <p
                className="mt-2 text-xs text-[var(--text-body)]"
                title="Temporary memory-safety limit on this server, not a permanent feature restriction."
              >
                Maximum {MAX_ADDITIONAL_GENES + 1} genes per search
              </p>
            ) : showAddGene ? (
              <div className="relative mt-2 max-w-xs">
                <GeneAutocompleteInput
                  value={additionalGeneDraft}
                  onChange={setAdditionalGeneDraft}
                  onSelect={addAdditionalGene}
                  allGenes={allGenes}
                  excludeFromSuggestions={[gene, ...additionalGenes]}
                  placeholder="Add another gene…"
                />
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setShowAddGene(true)}
                className="mt-2 text-xs text-[var(--text-body)] hover:text-[var(--text-heading)] transition-colors"
              >
                + Add another gene
              </button>
            )}
          </div>

          {/* Filters */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-5">
            {[
              { label: 'Disease Filter',           value: diseaseFilter, set: setDiseaseFilter, ph: 'e.g. lung, breast' },
              { label: 'Tissue Type',               value: lineageFilter, set: setLineageFilter, ph: 'e.g. lung, breast, epithelial' },
              { label: 'Exclude Genes (comma sep)', value: excludeGenes,  set: setExcludeGenes,  ph: 'e.g. KRAS, NRAS' },
            ].map(({ label, value, set, ph }) => (
              <div key={label}>
                <label className="text-[var(--text-body)] text-xs uppercase tracking-widest block mb-2">{label}</label>
                <input
                  type="text" value={value}
                  onChange={e => set(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleSearch()}
                  placeholder={ph}
                  className={inputCls}
                />
              </div>
            ))}
          </div>

          <div className="flex items-center gap-4 flex-wrap">
            <div className="flex items-center gap-2">
              <label className="text-[var(--text-body)] text-xs uppercase tracking-widest">Top</label>
              <select
                value={topN}
                onChange={e => setTopN(Number(e.target.value))}
                className="bg-cso-card border border-[var(--border)] text-[var(--text-heading)] px-3 py-2 rounded text-sm focus:outline-none"
              >
                {[5, 10, 20, 50].map(n => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
            <button
              onClick={handleSearch}
              disabled={!gene.trim() || loading}
              className="flex-1 bg-cso-teal font-semibold py-3 rounded hover:brightness-90 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
              style={{ color: 'var(--bg)' }}
            >
              {loading ? 'Running' : 'Run Analysis'}
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-6 py-8">
        {/* Loading — plain status line, not a decorative terminal window */}
        {loading && (
          <div className="flex items-center gap-3 mb-8">
            <div className="w-4 h-4 border border-[var(--border)] border-t-[var(--accent)] rounded-full animate-spin flex-shrink-0" />
            <span className="text-xs text-[var(--text-body)]">
              {LOADING_LINES[loadLine]}
            </span>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="bg-cso-card border border-[var(--accent-amber)] rounded p-4 text-[var(--accent-amber)] text-sm mb-6">
            {error}
          </div>
        )}

        {/* Results */}
        {allResults && !loading && (
          <>
            {/* Scoring transparency panel — accurate for both single- and
                multi-gene queries (weights_used is a flat dict for
                single-gene, {gene: {...weights}} for multi-gene; see
                describeWeights/WEIGHT_COMPONENT_INFO above). */}
            <div className="bg-cso-bg border border-[var(--border)] rounded p-4 mb-4 text-xs text-[var(--text-body)] leading-relaxed">
                <div className="text-[11px] uppercase tracking-[0.08em] font-semibold text-[var(--text-heading)] mb-2">
                  How Fit Score is computed
                </div>
                <p>
                  Each cell line's Fit Score combines whichever evidence
                  components are active for the queried gene(s): the set
                  and weighting is tuned per gene class (loss-of-function
                  genes weight <strong>Mutation Impact</strong> heavily,
                  amplification-driven oncogenes add{' '}
                  <strong>Copy Number</strong>, other genes weight
                  expression more heavily), all optimised by maximising
                  Mean Reciprocal Rank against a {VALIDATION_SET_SIZE}-gene
                  validated set of gene, cell-line associations from the
                  literature. <strong>RNA Expression</strong> measures
                  transcript abundance across HPA and DepMap;{' '}
                  <strong>Protein</strong> measures protein abundance from
                  CCLE proteomics; <strong>Data Quality</strong> reflects
                  cross-source agreement and data completeness;{' '}
                  <strong>Context</strong> rewards disease/tissue match to
                  your search filter; <strong>Mutation Impact</strong>{' '}
                  reflects damaging-variant status; <strong>Copy Number</strong>{' '}
                  reflects amplification status; and{' '}
                  <strong>Graph Centrality (RWR)</strong> reflects
                  random-walk-with-restart network proximity across the
                  gene/pathway/cell-line knowledge graph. GEO expression
                  acts as a separate confirmatory bonus (±10%, not one of
                  the weighted percentages above) when available.
                </p>
                <p className="mt-2">
                  Two methodology notes: pathway-coherence scoring
                  (checking whether a gene's KEGG pathway-neighbor genes
                  are also expressed in a cell line) was tested via four
                  separate methods and found NOT to improve ranking
                  accuracy, since post-translational activation mechanisms
                  aren't visible to transcriptional co-expression scoring,
                  so it is not part of the active weighting above.{' '}
                  <strong>Graph Centrality (RWR)</strong>, a structurally
                  different approach that captures network proximity
                  rather than co-expression, WAS found to significantly
                  improve rankings when combined with direct evidence, and
                  is active below.
                </p>
                {isMultiGene ? (
                  <div className="mt-2 space-y-1">
                    {[allResults.query?.gene, ...(allResults.query?.additional_genes ?? [])]
                      .filter(Boolean)
                      .map((g: string) => (
                        <p key={g}>
                          <strong>{g}</strong>: {describeWeights(w?.[g]) || 'weights unavailable'}
                        </p>
                      ))}
                  </div>
                ) : (
                  <p className="mt-2">
                    The percentages actually applied to{' '}
                    {allResults.query?.gene ?? gene}, a{' '}
                    {displayedResults?.results?.[0]?.gene_class?.replace(/_/g, ' ') ?? 'classified'}{' '}
                    gene: {describeWeights(w)}.
                  </p>
                )}
              </div>

            <div className="flex items-center justify-between mb-6">
              <div>
                <div className="text-[var(--text-heading)] font-bold text-lg">
                  Showing {displayedResults?.results.length} of {allResults.results?.length} loaded for{' '}
                  <span className="font-mono">
                    {isMultiGene
                      ? [allResults.query?.gene, ...(allResults.query?.additional_genes ?? [])].join(' + ')
                      : allResults.query?.gene}
                  </span>
                  {allResults.query?.disease_filter && (
                    <span className="text-[var(--text-body)] text-sm font-normal ml-2">
                      in {allResults.query.disease_filter}
                    </span>
                  )}
                </div>
                <div className="text-[var(--text-body)] text-xs mt-0.5 font-mono">
                  {isMultiGene
                    ? `${allResults.metadata?.n_excluded_missing_data ?? 0} lines excluded (missing data for ≥1 gene)`
                    : `${allResults.metadata?.total_candidates?.toLocaleString()} total candidates scored`}
                  {allResults.metadata?.execution_time_ms && ` · ${allResults.metadata.execution_time_ms}ms`}
                </div>
              </div>
              <div className="relative" ref={exportMenuRef}>
                <button
                  onClick={() => setExportOpen(o => !o)}
                  className="text-xs border border-[var(--border)] text-[var(--text-body)] hover:text-[var(--text-heading)] hover:border-[var(--text-heading)] px-3 py-1.5 rounded transition-colors"
                >
                  Export
                </button>
                {exportOpen && (
                  <div className="absolute right-0 mt-2 w-32 bg-cso-card border border-[var(--border)] rounded z-10 overflow-hidden">
                    {([['JSON', exportJSON], ['CSV', exportCSV], ['PDF', exportPDF]] as [string, () => void][]).map(([label, fn]) => (
                      <button
                        key={label}
                        onClick={() => { fn(); setExportOpen(false) }}
                        className="w-full text-left px-4 py-2 hover:bg-[var(--bg)] text-sm text-[var(--text-heading)] transition-colors"
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="space-y-4">
              {(displayedResults!.results as any[]).map((r: any) => (
                <ResultCard
                  key={r.cellosaurus_id}
                  result={r}
                  gene={allResults.query?.gene ?? gene}
                  additionalGenes={allResults.query?.additional_genes}
                  diseaseFilter={allResults.query?.disease_filter}
                  lineageFilter={allResults.query?.lineage_filter}
                  excludeGenes={
                    excludeGenes
                      ? excludeGenes.split(',').map(s => s.trim().toUpperCase()).filter(Boolean)
                      : undefined
                  }
                  onCellLineClick={setSelectedCVCL}
                />
              ))}
            </div>

            {/* Pathway-Connected Recommendations */}
            <div className="mt-8 pt-8 border-t border-[var(--border)]">
              <h2 className="text-[11px] uppercase tracking-[0.08em] font-semibold text-[var(--text-body)] mb-1">
                Pathway-Connected Recommendations
              </h2>
              <p className="text-xs text-[var(--text-body)] mb-4">
                Cell lines strong for genes that share a
                biological pathway with {allResults.query?.gene ?? gene}. These expand
                your experimental options beyond direct{' '}
                {allResults.query?.gene ?? gene} expression.
              </p>
              {pathwayResults === null ? (
                <div className="text-xs text-[var(--text-body)]">
                  No pathway-connected data available for this gene yet: the knowledge
                  graph currently only covers a curated set of validation genes.
                </div>
              ) : pathwayResults.length === 0 ? (
                <div className="text-xs text-[var(--text-body)]">
                  No pathway-connected cell lines found for this gene.
                </div>
              ) : (
                pathwayResults.map((r: any) => {
                  const top = r.connecting_genes?.[0]
                  const isDirect = top?.is_target
                  return (
                    <div
                      key={r.cellosaurus_id}
                      className="border border-[var(--border)] rounded p-3 mb-2 cursor-pointer hover:border-[var(--accent)] transition-colors"
                      onClick={() => setSelectedCVCL(r.cellosaurus_id)}
                    >
                      <div className="flex justify-between">
                        <div>
                          <span className="font-medium text-[var(--text-heading)] text-sm">
                            {r.official_name ?? r.cellosaurus_id}
                          </span>
                          {top && (
                            <span
                              className="ml-2 text-xs px-2 py-0.5 rounded border"
                              style={{
                                color: isDirect ? 'var(--accent-amber)' : 'var(--muted-state)',
                                borderColor: isDirect ? 'var(--accent-amber)' : 'var(--border)',
                              }}
                            >
                              {isDirect ? `direct: ${top.gene}` : `via ${top.gene}`}
                            </span>
                          )}
                        </div>
                        <span className="text-sm font-mono text-[var(--text-heading)]">
                          {(r.max_score ?? 0).toFixed(2)}
                        </span>
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          </>
        )}

        {/* Empty state */}
        {!allResults && !loading && !error && (
          <div className="text-center py-24">
            <div className="text-[var(--border)] text-6xl mb-5">⬡</div>
            <div className="text-[var(--text-body)] text-sm">
              Enter a gene symbol above and press{' '}
              <span className="text-[var(--text-heading)] font-semibold">Run Analysis</span>
            </div>
          </div>
        )}
      </div>

      {selectedCVCL && (
        <SlideOver cellosaurus_id={selectedCVCL} onClose={() => setSelectedCVCL(null)} />
      )}
    </div>
  )
}
