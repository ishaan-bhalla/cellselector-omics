import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import ResultCard from '../components/ResultCard'
import SlideOver from '../components/SlideOver'

const LOADING_LINES = [
  '> Resolving gene symbol…',
  '> Computing RNA expression scores…',
  '> Applying protein expression weights…',
  '> Running GEO cross-validation…',
  '> Ranking 2,076 cell lines…',
  '> Computing similarity alternatives…',
  '> Analysis complete.',
]

export default function Search() {
  const [gene, setGene] = useState('')
  const [geneInfo, setGeneInfo] = useState<any>(null)
  const [geneLoading, setGeneLoading] = useState(false)
  const [diseaseFilter, setDiseaseFilter] = useState('')
  const [lineageFilter, setLineageFilter] = useState('')
  const [excludeGenes, setExcludeGenes] = useState('')
  const [topN, setTopN] = useState(10)
  const [results, setResults] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [loadLine, setLoadLine] = useState(0)
  const [selectedCVCL, setSelectedCVCL] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!gene.trim()) { setGeneInfo(null); return }
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(async () => {
      setGeneLoading(true)
      try {
        const r = await api.searchGene(gene.trim().toUpperCase())
        setGeneInfo(r)
      } catch {
        setGeneInfo(null)
      } finally {
        setGeneLoading(false)
      }
    }, 300)
  }, [gene])

  useEffect(() => {
    if (!loading) { setLoadLine(0); return }
    const id = setInterval(() => setLoadLine(l => Math.min(l + 1, LOADING_LINES.length - 1)), 650)
    return () => clearInterval(id)
  }, [loading])

  const handleSearch = async () => {
    const g = gene.trim().toUpperCase()
    if (!g) return
    setLoading(true); setResults(null); setError(null)
    try {
      const r = await api.recommendClassical({
        gene: g,
        disease_filter: diseaseFilter.trim() || undefined,
        lineage_filter: lineageFilter.trim() || undefined,
        exclude_genes: excludeGenes
          ? excludeGenes.split(',').map(s => s.trim().toUpperCase()).filter(Boolean)
          : undefined,
        top_n: topN,
      })
      if (r.detail) throw new Error(r.detail)
      setResults(r)
    } catch (e: any) {
      setError(e?.message ?? 'Request failed. Is the API running on port 8001?')
    } finally {
      setLoading(false)
    }
  }

  const exportJSON = () => {
    if (!results) return
    const blob = new Blob([JSON.stringify(results, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `cellselector_${gene}_${new Date().toISOString().split('T')[0]}.json`
    a.click(); URL.revokeObjectURL(url)
  }

  const exportCSV = () => {
    if (!results?.results) return
    const headers = ['rank','cellosaurus_id','official_name','final_score','rna_score',
      'protein_score','quality_score','context_score','n_sources','gene_class','disease','lineage']
    const rows = (results.results as any[]).map((r: any) => headers.map(h => r[h] ?? '').join(','))
    const csv = [headers.join(','), ...rows].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `cellselector_${gene}_${new Date().toISOString().split('T')[0]}.csv`
    a.click(); URL.revokeObjectURL(url)
  }

  const geneFound = geneInfo?.found === true
  const sourcesFound = geneFound
    ? Object.entries(geneInfo.sources as Record<string, boolean>)
        .filter(([, v]) => v).map(([k]) => k).join(' · ')
    : ''

  const inputCls = `w-full bg-white border border-[#D2D2D7] text-[#1D1D1F] px-4 py-2.5 rounded-xl text-sm focus:outline-none focus:border-[#1D1D1F] transition-colors placeholder-[#D2D2D7]`

  return (
    <div className="min-h-screen bg-white pt-24">
      {/* Search panel */}
      <div className="bg-white border-b border-[#D2D2D7]">
        <div className="max-w-3xl mx-auto px-6 pb-8">
          <p className="text-[#6E6E73] text-xs tracking-[0.2em] uppercase mb-2">Cell Line Recommender</p>
          <h1 className="text-[#1D1D1F] text-3xl font-bold mb-8">Search Tool</h1>

          {/* Gene input */}
          <div className="mb-5">
            <label className="text-[#6E6E73] text-xs uppercase tracking-widest block mb-2">Gene Name</label>
            <div className="relative">
              <input
                type="text"
                value={gene}
                onChange={e => setGene(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSearch()}
                placeholder="e.g. EGFR, BRCA1, KIT"
                autoFocus
                className="w-full bg-white border border-[#D2D2D7] text-[#1D1D1F] font-mono text-lg px-4 py-3 rounded-xl focus:outline-none focus:border-[#1D1D1F] transition-colors placeholder-[#D2D2D7]"
                style={{ boxShadow: gene ? '0 0 0 3px rgba(29,29,31,0.06)' : undefined }}
              />
              {geneLoading && (
                <div className="absolute right-3.5 top-4">
                  <div className="w-4 h-4 border border-[#D2D2D7] border-t-[#1D1D1F] rounded-full animate-spin" />
                </div>
              )}
            </div>
            {geneInfo && !geneLoading && (
              <div className={`mt-2 text-xs font-mono ${geneFound ? 'text-[#2D6A4F]' : 'text-[#C62828]'}`}>
                {geneFound
                  ? `✓ ${gene.toUpperCase()} — ${sourcesFound} — ${geneInfo.total_cell_lines_with_data?.toLocaleString()} cell lines`
                  : `✗ ${gene.toUpperCase()} not found in any omics source`}
              </div>
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
                <label className="text-[#6E6E73] text-xs uppercase tracking-widest block mb-2">{label}</label>
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
              <label className="text-[#6E6E73] text-xs uppercase tracking-widest">Top</label>
              <select
                value={topN}
                onChange={e => setTopN(Number(e.target.value))}
                className="bg-white border border-[#D2D2D7] text-[#1D1D1F] px-3 py-2 rounded-xl text-sm focus:outline-none"
              >
                {[5, 10, 20, 50].map(n => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
            <button
              onClick={handleSearch}
              disabled={!gene.trim() || loading}
              className="flex-1 bg-[#1D1D1F] text-white font-semibold py-3 rounded-xl hover:bg-[#333333] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {loading ? 'Running…' : 'Run Analysis →'}
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-6 py-8">
        {/* Loading terminal */}
        {loading && (
          <div className="bg-[#F5F5F7] border border-[#D2D2D7] rounded-xl p-4 font-mono text-xs mb-8">
            {LOADING_LINES.slice(0, loadLine + 1).map((line, i) => (
              <div key={i} className="text-[#6E6E73]">
                {line}
                {i === loadLine && i < LOADING_LINES.length - 1 && (
                  <span className="animate-pulse ml-0.5 text-[#1D1D1F]">█</span>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="bg-[#FCE4EC] border border-[#F8BBD9] rounded-xl p-4 text-[#C62828] text-sm mb-6">
            {error}
          </div>
        )}

        {/* Results */}
        {results && !loading && (
          <>
            <div className="flex items-center justify-between mb-6">
              <div>
                <div className="text-[#1D1D1F] font-bold text-lg">
                  {results.results?.length} results for{' '}
                  <span className="font-mono">{results.query?.gene}</span>
                  {results.query?.disease_filter && (
                    <span className="text-[#6E6E73] text-sm font-normal ml-2">
                      in {results.query.disease_filter}
                    </span>
                  )}
                </div>
                <div className="text-[#6E6E73] text-xs mt-0.5 font-mono">
                  {results.metadata?.total_candidates?.toLocaleString()} candidates scored
                  {results.metadata?.execution_time_ms && ` · ${results.metadata.execution_time_ms}ms`}
                </div>
              </div>
              <div className="flex gap-2">
                {[['Export JSON', exportJSON], ['Export CSV', exportCSV]].map(([label, fn]) => (
                  <button
                    key={label as string}
                    onClick={fn as () => void}
                    className="text-xs border border-[#D2D2D7] text-[#6E6E73] hover:text-[#1D1D1F] hover:border-[#1D1D1F] px-3 py-1.5 rounded-lg transition-colors"
                  >
                    {label as string}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-4">
              {(results.results as any[]).map((r: any) => (
                <ResultCard
                  key={r.cellosaurus_id}
                  result={r}
                  gene={results.query?.gene ?? gene}
                  diseaseFilter={results.query?.disease_filter}
                  excludeGenes={
                    excludeGenes
                      ? excludeGenes.split(',').map(s => s.trim().toUpperCase()).filter(Boolean)
                      : undefined
                  }
                  onCellLineClick={setSelectedCVCL}
                />
              ))}
            </div>
          </>
        )}

        {/* Empty state */}
        {!results && !loading && !error && (
          <div className="text-center py-24">
            <div className="text-[#D2D2D7] text-6xl mb-5">⬡</div>
            <div className="text-[#6E6E73] text-sm">
              Enter a gene symbol above and press{' '}
              <span className="text-[#1D1D1F] font-semibold">Run Analysis</span>
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
