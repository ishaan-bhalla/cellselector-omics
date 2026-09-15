import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import ResultCard from '../components/ResultCard'
import ResultCardGrid from '../components/ResultCardGrid'
import ResultCardCompact from '../components/ResultCardCompact'
import SlideOver from '../components/SlideOver'
import Reveal from '../components/Reveal'
import AutocompleteInput from '../components/AutocompleteInput'
import type { ViewMode } from '../utils/viewMode'
import { loadSearchForm, saveSearchForm, loadSearchResults, saveSearchResults } from '../utils/searchState'

const LOADING_LINES = [
  'Resolving gene symbol',
  'Computing RNA expression scores',
  'Applying protein expression weights',
  'Running GEO cross-validation',
  'Ranking 2,076 cell lines',
  'Computing similarity alternatives',
  'Analysis complete',
]

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

interface Props {
  viewMode: ViewMode
}

export default function Search({ viewMode }: Props) {
  // Item 6: each lazy initializer reads sessionStorage exactly once, on
  // mount — see utils/searchState.ts. Restores the previous query/
  // filters/results after navigating Search -> Home/About/Data -> Search.
  const [gene, setGene] = useState(() => loadSearchForm().gene ?? '')
  // Per-gene stats (found/sources/cell-line count) for the gene actually
  // SELECTED from the dropdown — no longer fetched per keystroke, so
  // there's no async request in flight during typing to race against.
  const [geneInfo, setGeneInfo] = useState<any>(null)
  const [geneLoading, setGeneLoading] = useState(false)
  const [diseaseFilter, setDiseaseFilter] = useState(() => loadSearchForm().diseaseFilter ?? '')
  // Tissue Type (lineage_filter) removed per user testing feedback — see
  // the Item 4 note further down at the request-building call site for
  // what was checked before removing it.
  const [excludeGenes, setExcludeGenes] = useState<string[]>(() => loadSearchForm().excludeGenes ?? [])
  const [excludeGeneDraft, setExcludeGeneDraft] = useState('')
  const [showAddExclude, setShowAddExclude] = useState(false)
  // Clamped to 20 (Item 9, STEP 3 removed the "Top 50" option) — guards
  // against a stale topN: 50 restored from a session persisted before
  // this change, which the <select> below no longer offers as an option.
  const [topN, setTopN] = useState(() => Math.min(loadSearchForm().topN ?? 10, 20))
  const [allResults, setAllResults] = useState<any>(() => loadSearchResults())
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
  // Distinct disease values, fetched once on mount the same way — powers
  // the Disease Filter's dropdown (Item 1), replacing the old free-text
  // input with the same client-side-filtered pattern as the gene fields.
  const [diseases, setDiseases] = useState<string[]>([])
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
  const [additionalGenes, setAdditionalGenes] = useState<string[]>(() => loadSearchForm().additionalGenes ?? [])
  const [additionalGeneDraft, setAdditionalGeneDraft] = useState('')
  const [showAddGene, setShowAddGene] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const exportMenuRef = useRef<HTMLDivElement>(null)
  // viewMode/onViewModeChange now come in as props — lifted to App.tsx so
  // the corrected-direction Navbar can host the control in its centre
  // zone and stay in sync in real time (see App.tsx).
  // Keeps the loading takeover MOUNTED for a brief window after `loading`
  // flips false, so its collapse (Part 4) is a CSS transition rather than
  // an instant unmount — see the takeover's own maxHeight/opacity, which
  // key off `loading` directly while this only controls whether it's in
  // the DOM at all.
  const [takeoverVisible, setTakeoverVisible] = useState(false)

  useEffect(() => {
    api.getAllGenes()
      .then(d => setAllGenes(d.genes ?? []))
      .catch(() => setAllGenes([]))
    api.getAllDiseases()
      .then(d => setDiseases(d.diseases ?? []))
      .catch(() => setDiseases([]))
  }, [])

  // Item 6: restores the "found, N sources, N cell lines" confirmation
  // line for a gene carried over from a previous visit — geneInfo itself
  // isn't persisted (not in the task's explicit scope list), so this
  // just re-runs the same lookup selecting a gene already triggers,
  // mount-only (the `[]` deps — this must NOT re-fire on every `gene`
  // change, or it would clobber selectGene's own normal per-selection
  // fetch).
  useEffect(() => {
    if (gene) selectGene(gene)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Item 6: persists the search form (cheap, updates per keystroke) and
  // the last-fetched results (potentially much larger, so kept in its own
  // effect keyed only on allResults — doesn't re-serialize on every
  // keystroke of an unrelated field) to sessionStorage, so navigating
  // Search -> Home/About/Data -> Search restores the full previous state,
  // not just the input values with an empty results area.
  useEffect(() => {
    saveSearchForm({ gene, additionalGenes, diseaseFilter, excludeGenes, topN })
  }, [gene, additionalGenes, diseaseFilter, excludeGenes, topN])

  useEffect(() => {
    saveSearchResults(allResults)
  }, [allResults])

  useEffect(() => {
    if (loading) {
      setTakeoverVisible(true)
      return
    }
    const t = setTimeout(() => setTakeoverVisible(false), 420)
    return () => clearTimeout(t)
  }, [loading])

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

  // Exclude Genes — same chip pattern as additionalGenes (Item 1), no cap
  // (there was never one on the old free-text comma-separated field this
  // replaces, so none is introduced here either).
  const addExcludeGene = (g: string) => {
    setExcludeGeneDraft('')
    if (g === gene || excludeGenes.includes(g)) return
    setExcludeGenes(prev => [...prev, g])
  }

  const removeExcludeGene = (g: string) => {
    setExcludeGenes(prev => prev.filter(x => x !== g))
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

    // excludeGenes is now a real string[] (Item 1's chip picker), so no
    // parsing is needed here any more — was previously split from a
    // comma-separated free-text field.
    if (excludeGenes.includes(g)) {
      setError(`Cannot search for ${g} and exclude it at the same time.`)
      return
    }

    setLoading(true); setAllResults(null); setError(null)
    try {
      const diseaseFilterVal = diseaseFilter.trim() || undefined
      // Pathway-Connected Recommendations (the section that used to
      // render below the main results, fetched here via
      // api.cellLinesViaPathway alongside the main search) was removed
      // per user testing feedback (Item 7) — rigorous evaluation
      // established pathway-coherence scoring doesn't earn a dedicated,
      // prominent UI section (see ranker.py / pathway_scorer.py; the
      // backend scoring itself is UNTOUCHED, still correctly weighted for
      // loss-of-function genes — this was a UI declutter only). The
      // second Promise.all leg and pathwayResults state are gone with it.
      const r = await api.recommendClassical({
        gene: g,
        // additionalGenes is always a real array (possibly empty) — sent
        // as-is, matching what additional_genes: list[str] =
        // Field(default_factory=list) on the backend expects. An empty
        // array here takes the EXACT SAME code path as before this
        // change (see api/main.py: `if body.additional_genes:` is False
        // for []), so a search with nothing added is unaffected.
        additional_genes: additionalGenes,
        disease_filter: diseaseFilterVal,
        // lineage_filter removed (Item 4) — Tissue Type no longer
        // collected, so nothing is sent for it any more.
        exclude_genes: excludeGenes.length ? excludeGenes : undefined,
        // Reduced from 50 to cut backend work — see the timing
        // investigation report. The dropdown no longer offers "Top 50"
        // at all (Item 9), so this now always matches the largest
        // selectable option.
        top_n: 20,
      })
      if (r.detail) throw new Error(r.detail)
      setAllResults(r)
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
          <p className="text-[var(--text-body)] text-xs tracking-[0.2em] uppercase mb-3">Cell Line Recommender</p>
          <h1 className="font-bold mb-8" style={{ fontSize: 'clamp(2rem, 4.5vw, 3.25rem)', color: 'var(--text-heading)', letterSpacing: '-0.01em' }}>Search Tool</h1>

          {/* Gene input — client-side-filtered dropdown via the shared
              AutocompleteInput. Item 5: the additional-gene slot sits
              directly BESIDE the primary field (same flex row, same
              flex-1 width, same input styling) rather than appearing
              below it in a different style — the "+ Add another gene"
              trigger, the open draft input, and the selected-gene chip
              all render AT that second position, never elsewhere, so the
              two consistently read as one adjacent pair regardless of
              which of those three states slot 2 is in. */}
          <div className="mb-5">
            <label className="text-[var(--text-body)] text-xs uppercase tracking-widest block mb-2">
              Gene Name{additionalGenes.length > 0 || showAddGene ? ' + Additional Gene' : ''}
            </label>
            <div className="flex gap-3 items-start">
              <div className="relative flex-1">
                <AutocompleteInput
                  value={gene}
                  onChange={v => { setGene(v); setGeneInfo(null) }}
                  onSelect={selectGene}
                  options={allGenes}
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

              {additionalGenes.length > 0 ? (
                // Selected — rendered in the exact same box styling as the
                // AutocompleteInput's own <input> (same border/height/
                // font), so it still reads as the second half of the
                // pair, not a chip stuck somewhere else.
                <div className="flex-1 flex items-center justify-between bg-cso-card border border-[var(--border)] rounded px-4 py-3">
                  <span className="font-mono text-lg text-[var(--text-heading)]">{additionalGenes[0]}</span>
                  <button
                    type="button"
                    onClick={() => removeAdditionalGene(additionalGenes[0])}
                    aria-label={`Remove ${additionalGenes[0]}`}
                    className="text-[var(--text-body)] hover:text-[var(--accent-amber)] transition-colors leading-none text-xl"
                  >
                    ×
                  </button>
                </div>
              ) : showAddGene ? (
                <div className="relative flex-1">
                  <AutocompleteInput
                    value={additionalGeneDraft}
                    onChange={setAdditionalGeneDraft}
                    onSelect={addAdditionalGene}
                    options={allGenes}
                    excludeFromSuggestions={[gene]}
                    placeholder="Add another gene…"
                    autoFocus
                  />
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setShowAddGene(true)}
                  className="flex-1 flex items-center justify-center text-sm text-[var(--text-body)] hover:text-[var(--text-heading)] border border-dashed border-[var(--border)] hover:border-[var(--text-heading)] rounded px-4 py-3 transition-colors"
                  style={{ minHeight: 52 }}
                >
                  + Add another gene
                </button>
              )}
            </div>
            {geneInfo && !geneLoading && (
              <div className="mt-2 text-xs font-mono text-[var(--text-heading)]">
                {`${geneInfo.gene ?? gene.toUpperCase()}, ${sourcesFound}, ${geneInfo.total_cell_lines_with_data?.toLocaleString()} cell lines`}
              </div>
            )}
            {additionalGenes.length >= MAX_ADDITIONAL_GENES && (
              <p
                className="mt-2 text-xs text-[var(--text-body)]"
                title="Temporary memory-safety limit on this server, not a permanent feature restriction."
              >
                Maximum {MAX_ADDITIONAL_GENES + 1} genes per search
              </p>
            )}
          </div>

          {/* Filters — Disease Filter now a dropdown of real distinct
              disease values (Item 1); Exclude Genes now a multi-select
              chip picker reusing the exact gene list (Item 1); Tissue
              Type removed entirely (Item 4). Each still carries a
              bracket-syntax state marker (Part 6). */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">
            <div>
              <label className="text-[var(--text-body)] text-xs uppercase tracking-widest flex items-center justify-between mb-2">
                Disease Filter
                <span className="font-mono text-[10px]" style={{ color: diseaseFilter.trim() ? 'var(--text-heading)' : 'var(--muted-state)' }}>
                  DISEASE:[{diseaseFilter.trim() ? 'SET' : '—'}]
                </span>
              </label>
              <AutocompleteInput
                value={diseaseFilter}
                onChange={setDiseaseFilter}
                onSelect={setDiseaseFilter}
                options={diseases}
                matchAnywhere
                placeholder="e.g. Lung Cancer, Breast Cancer"
                size="sm"
              />
            </div>

            <div>
              <label className="text-[var(--text-body)] text-xs uppercase tracking-widest flex items-center justify-between mb-2">
                Exclude Genes
                <span className="font-mono text-[10px]" style={{ color: excludeGenes.length ? 'var(--text-heading)' : 'var(--muted-state)' }}>
                  EXCLUDE:[{excludeGenes.length ? 'SET' : '—'}]
                </span>
              </label>
              {excludeGenes.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {excludeGenes.map(g => (
                    <span
                      key={g}
                      className="inline-flex items-center gap-1.5 text-xs font-mono bg-[var(--bg)] text-[var(--text-heading)] px-2.5 py-1 rounded-full"
                    >
                      {g}
                      <button
                        type="button"
                        onClick={() => removeExcludeGene(g)}
                        aria-label={`Remove ${g}`}
                        className="text-[var(--text-body)] hover:text-[var(--accent-amber)] transition-colors leading-none"
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              )}
              {showAddExclude ? (
                <AutocompleteInput
                  value={excludeGeneDraft}
                  onChange={setExcludeGeneDraft}
                  onSelect={addExcludeGene}
                  options={allGenes}
                  excludeFromSuggestions={[gene, ...excludeGenes]}
                  placeholder="Add a gene to exclude…"
                  autoFocus
                  size="sm"
                />
              ) : (
                <button
                  type="button"
                  onClick={() => setShowAddExclude(true)}
                  className={`${inputCls} text-left text-[var(--text-body)] hover:border-[var(--text-heading)]`}
                >
                  + Add gene to exclude…
                </button>
              )}
            </div>
          </div>

          <div className="flex items-center gap-4 flex-wrap">
            <div className="flex items-center gap-2">
              <label className="text-[var(--text-body)] text-xs uppercase tracking-widest">Top</label>
              <select
                value={topN}
                onChange={e => setTopN(Number(e.target.value))}
                className="bg-cso-card border border-[var(--border)] text-[var(--text-heading)] px-3 py-2 rounded text-sm focus:outline-none"
              >
                {/* "Top 50" removed (Item 9, STEP 3) — the backend fetch
                    is capped at top_n: 20 (see handleSearch), so 50 was
                    always a dead/mismatched option anyway (it never
                    displayed more than the 20 actually fetched). */}
                {[5, 10, 20].map(n => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
            <button
              onClick={handleSearch}
              disabled={!gene.trim() || loading}
              className="flex-1 bg-cso-heading font-semibold py-3 rounded hover:opacity-90 transition-opacity disabled:opacity-40 disabled:cursor-not-allowed"
              style={{ color: 'var(--bg)' }}
            >
              {loading ? 'Running' : 'Run Analysis'}
            </button>
          </div>
        </div>
      </div>

      {/* Search-execution takeover (Part 4) — a genuine full-width moment
          while a search runs, not a small box below the form: expands to
          become the visual focus, each console line stages in after the
          last (see LOADING_LINES.slice + the .console-line animation),
          then collapses smoothly (maxHeight/opacity transition, kept
          mounted an extra ~420ms via takeoverVisible so the collapse is
          visible rather than an instant unmount) into the results below. */}
      {takeoverVisible && (
        <div
          className="w-full overflow-hidden"
          style={{
            maxHeight: loading ? 640 : 0,
            opacity: loading ? 1 : 0,
            borderBottom: loading ? '1px solid var(--border)' : '1px solid transparent',
            transition: 'max-height 420ms ease, opacity 280ms ease, border-color 420ms ease',
          }}
        >
          <div className="max-w-4xl mx-auto px-6" style={{ paddingTop: 96, paddingBottom: 96 }}>
            <div className="font-mono" style={{ fontSize: 'clamp(1rem, 2.4vw, 1.65rem)' }}>
              {LOADING_LINES.slice(0, loadLine + 1).map((line, i) => {
                const isCurrent = i === loadLine
                return (
                  <div
                    key={i}
                    className="console-line"
                    style={{
                      marginBottom: 14,
                      color: isCurrent ? 'var(--text-heading)' : 'var(--text-body)',
                      opacity: isCurrent ? 1 : 0.45,
                    }}
                  >
                    {line}
                    {isCurrent && i < LOADING_LINES.length - 1 && (
                      <span className="animate-pulse ml-1" style={{ color: 'var(--text-heading)' }}>_</span>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      <div className="max-w-5xl mx-auto px-6 py-8">
        {/* Error */}
        {error && (
          <div className="bg-cso-card border border-[var(--accent-amber)] rounded p-4 text-[var(--accent-amber)] text-sm mb-6">
            {error}
          </div>
        )}

        {/* Results */}
        {allResults && !loading && (
          <>
            {/* The old permanent "How Fit Score is computed" panel is gone
                (Item 2) — that explanation is now a hover/focus popover
                anchored to each card's own Fit Score element (FitRing or
                its numeral), showing THAT card's real weights via
                weightsUsed rather than one static block above every
                result. See components/FitScoreExplanation.tsx and
                HoverPopover.tsx, wired into ResultCard/ResultCardGrid/
                ResultCardCompact below. */}

            <div className="flex items-start justify-between mb-4 gap-4 flex-wrap">
              <div>
                <div style={{ color: 'var(--text-heading)', fontWeight: 700, fontSize: '1.75rem', letterSpacing: '-0.01em', lineHeight: 1.15 }}>
                  Showing {displayedResults?.results.length} of {allResults.results?.length} for{' '}
                  <span className="font-mono">
                    {isMultiGene
                      ? [allResults.query?.gene, ...(allResults.query?.additional_genes ?? [])].join(' + ')
                      : allResults.query?.gene}
                  </span>
                  {allResults.query?.disease_filter && (
                    <span className="text-[var(--text-body)] text-base font-normal ml-2">
                      in {allResults.query.disease_filter}
                    </span>
                  )}
                </div>
                <div className="text-[var(--text-body)] text-xs mt-1.5 font-mono">
                  {isMultiGene
                    ? `${allResults.metadata?.n_excluded_missing_data ?? 0} lines excluded (missing data for ≥1 gene)`
                    : `${allResults.metadata?.total_candidates?.toLocaleString()} total candidates scored`}
                  {allResults.metadata?.execution_time_ms && ` · ${allResults.metadata.execution_time_ms}ms`}
                </div>
              </div>
              <div className="flex items-center gap-3">
                {/* View mode is now chosen from the navbar's centre zone
                    (Part 2 of the corrected direction) — `viewMode` prop
                    still drives which layout renders below. */}
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
            </div>

            {/* Status bar — moved here, directly above the results list
                (Item 8), so it's seen before scrolling through results
                rather than only after. Same thin, dense chrome-bar
                styling as the navbar, bracket-syntax metadata showing
                live session/query state rather than decoration. */}
            <div
              className="bg-cso-bg flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 mb-4 font-mono"
              style={{ border: '1px solid var(--border)', fontSize: 11 }}
            >
              <span style={{ color: 'var(--text-heading)' }}>
                RESULTS:[{displayedResults?.results.length ?? 0}]
              </span>
              <span style={{ color: 'var(--text-body)' }}>
                {isMultiGene
                  ? [allResults.query?.gene, ...(allResults.query?.additional_genes ?? [])].join('+')
                  : allResults.query?.gene}
                {' · '}
                {allResults.metadata?.total_candidates?.toLocaleString() ?? '0'} CANDIDATES
              </span>
              <span style={{ color: 'var(--text-body)' }}>
                FILTERS:[{(diseaseFilter.trim() || excludeGenes.length) ? 'ON' : 'OFF'}]
                {'  '}
                MULTI-GENE:[{isMultiGene ? 'ON' : 'OFF'}]
              </span>
            </div>

            {/* Three real, distinct layouts over the same result data (Part
                3) — not decoration: LIST is the existing full-detail
                ResultCard, GRID a 2-column compact card, COMPACT a dense
                single-line row. Each card reveals on scroll (Part 2). */}
            {viewMode === 'list' && (
              <div className="space-y-4">
                {(displayedResults!.results as any[]).map((r: any, i: number) => (
                  <Reveal key={r.cellosaurus_id} delay={Math.min(i, 6) * 40}>
                    <ResultCard
                      result={r}
                      gene={allResults.query?.gene ?? gene}
                      additionalGenes={allResults.query?.additional_genes}
                      diseaseFilter={allResults.query?.disease_filter}
                      excludeGenes={excludeGenes.length ? excludeGenes : undefined}
                      weightsUsed={w}
                      onCellLineClick={setSelectedCVCL}
                    />
                  </Reveal>
                ))}
              </div>
            )}

            {viewMode === 'grid' && (
              // 96-well microplate (corrected direction #2, replacing the
              // prior edge-to-edge panel for GRID specifically) — a real,
              // visible gap between circular wells, not the gutter-less
              // hairline grid used elsewhere; that's a deliberate
              // difference, not an inconsistency. Column count scales
              // with viewport toward the ~8-column proportion of a real
              // 96-well plate, fewer columns on narrower screens.
              <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 lg:grid-cols-8 gap-3">
                {(displayedResults!.results as any[]).map((r: any, i: number) => (
                  <Reveal key={r.cellosaurus_id} delay={Math.min(i, 12) * 20}>
                    <ResultCardGrid
                      result={r}
                      gene={allResults.query?.gene ?? gene}
                      additionalGenes={allResults.query?.additional_genes}
                      diseaseFilter={allResults.query?.disease_filter}
                      weightsUsed={w}
                      isMultiGene={isMultiGene}
                      onCellLineClick={setSelectedCVCL}
                    />
                  </Reveal>
                ))}
              </div>
            )}

            {viewMode === 'compact' && (
              <Reveal>
                <div className="bg-cso-card border border-[var(--border)] rounded overflow-hidden">
                  {(displayedResults!.results as any[]).map((r: any) => (
                    <ResultCardCompact
                      key={r.cellosaurus_id}
                      result={r}
                      gene={allResults.query?.gene ?? gene}
                      additionalGenes={allResults.query?.additional_genes}
                      diseaseFilter={allResults.query?.disease_filter}
                      weightsUsed={w}
                      onCellLineClick={setSelectedCVCL}
                    />
                  ))}
                </div>
              </Reveal>
            )}
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
