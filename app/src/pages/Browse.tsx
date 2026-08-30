import { useEffect, useState } from 'react'
import { api } from '../api/client'

const PAGE_SIZE = 20

// The four omics data sources shown as coloured dots in the Sources column
const SOURCES = [
  { key: 'has_hpa_expr',    label: 'HPA',        color: '#E63946' },
  { key: 'has_depmap_expr', label: 'DepMap',      color: '#457B9D' },
  { key: 'has_geo_expr',    label: 'GEO',         color: '#2D6A4F' },
  { key: 'has_proteomics',  label: 'Proteomics',  color: '#8B5CF6' },
]

export default function Browse() {
  const [rawSearch, setRawSearch] = useState('')   // immediate input value
  const [query, setQuery]         = useState('')   // debounced — drives API calls
  const [page, setPage]           = useState(0)
  const [data, setData]           = useState<any>(null)
  const [loading, setLoading]     = useState(false)

  // Debounce: commit rawSearch → query 300 ms after typing stops, reset to page 0
  useEffect(() => {
    const t = setTimeout(() => {
      setQuery(rawSearch)
      setPage(0)
    }, 300)
    return () => clearTimeout(t)
  }, [rawSearch])

  // Fetch whenever the committed query or page changes
  useEffect(() => {
    let alive = true
    setLoading(true)
    api.browseCellLines({ search: query || undefined, limit: PAGE_SIZE, offset: page * PAGE_SIZE })
      .then(r  => { if (alive) setData(r) })
      .catch(() => { if (alive) setData(null) })
      .finally(()  => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [query, page])

  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0
  const start      = page * PAGE_SIZE + 1
  const end        = data ? Math.min((page + 1) * PAGE_SIZE, data.total) : 0

  const downloadCSV = async () => {
    const r = await api.browseCellLines({ search: query || undefined, limit: 5000, offset: 0 })
    const headers = [
      'cellosaurus_id', 'official_name', 'disease', 'lineage',
      'confidence', 'evidence_count',
      'has_hpa_expr', 'has_depmap_expr', 'has_geo_expr', 'has_proteomics',
      'has_mutations', 'has_fusions',
    ]
    const rows = (r.results as any[]).map((row: any) =>
      headers.map(h => JSON.stringify(row[h] ?? '')).join(',')
    )
    const csv  = [headers.join(','), ...rows].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href = url
    a.download = `cell_lines${query ? '_' + query.replace(/\s+/g, '_') : ''}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="min-h-screen bg-white pt-24">

      {/* ── Header panel ── */}
      <div className="bg-white border-b border-[#D2D2D7]">
        <div className="max-w-6xl mx-auto px-6 pb-6">
          <p className="text-[#6E6E73] text-xs tracking-[0.2em] uppercase mb-2">Cell Line Database</p>
          <div className="flex items-end justify-between gap-4 mb-5">
            <div>
              <h1 className="text-[#1D1D1F] text-3xl font-bold">All Cell Lines</h1>
              <p className="text-[#6E6E73] text-sm mt-1 font-mono">
                {data
                  ? `${data.total.toLocaleString()} cell lines${query ? ` matching "${query}"` : ''}`
                  : loading ? 'Loading…' : ''}
              </p>
            </div>
            <button
              onClick={downloadCSV}
              disabled={!data}
              className="flex-shrink-0 text-sm border border-[#D2D2D7] text-[#6E6E73] hover:text-[#1D1D1F] hover:border-[#1D1D1F] px-4 py-2 rounded-xl transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Download CSV
            </button>
          </div>

          <input
            type="text"
            value={rawSearch}
            onChange={e => setRawSearch(e.target.value)}
            placeholder="Filter by name, disease or lineage…"
            className="w-full bg-white border border-[#D2D2D7] text-[#1D1D1F] px-4 py-2.5 rounded-xl text-sm focus:outline-none focus:border-[#1D1D1F] transition-colors placeholder-[#D2D2D7]"
          />
        </div>
      </div>

      {/* ── Table ── */}
      <div className="max-w-6xl mx-auto px-6 py-6">

        {/* Source dot legend */}
        <div className="flex items-center gap-4 mb-3">
          {SOURCES.map(s => (
            <div key={s.key} className="flex items-center gap-1.5">
              <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: s.color }} />
              <span className="text-[#6E6E73] text-xs">{s.label}</span>
            </div>
          ))}
          <span className="text-[#D2D2D7] text-xs ml-2">● = no data</span>
        </div>

        {data && data.results.length > 0 && (
          <div
            className="overflow-x-auto rounded-xl border border-[#D2D2D7]"
            style={{ boxShadow: '0 1px 8px rgba(0,0,0,0.04)', opacity: loading ? 0.5 : 1, transition: 'opacity 0.15s' }}
          >
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="bg-[#F5F5F7] border-b border-[#D2D2D7]">
                  {['Cell Line', 'CVCL ID', 'Disease', 'Lineage', 'Confidence', 'Sources'].map(h => (
                    <th
                      key={h}
                      className={`px-4 py-3 font-semibold text-[#1D1D1F] text-xs uppercase tracking-wider whitespace-nowrap
                        ${h === 'Confidence' || h === 'Sources' ? 'text-right' : 'text-left'}`}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(data.results as any[]).map((row: any, i: number) => (
                  <tr
                    key={row.cellosaurus_id}
                    className={`border-b border-[#F5F5F7] transition-colors ${i % 2 === 0 ? 'bg-white' : 'bg-[#FAFAFA]'} hover:bg-[#F5F5F7]`}
                  >
                    <td className="px-4 py-2.5 font-medium text-[#1D1D1F] whitespace-nowrap">
                      {row.official_name || '—'}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-xs text-[#6E6E73] whitespace-nowrap">
                      {row.cellosaurus_id}
                    </td>
                    <td className="px-4 py-2.5 text-[#6E6E73] text-xs max-w-[200px] truncate" title={row.disease}>
                      {row.disease || '—'}
                    </td>
                    <td className="px-4 py-2.5 text-[#6E6E73] text-xs whitespace-nowrap">
                      {row.lineage || '—'}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-sm text-[#1D1D1F] whitespace-nowrap">
                      {row.confidence != null ? `${(row.confidence * 100).toFixed(0)}%` : '—'}
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        {SOURCES.map(s => (
                          <span
                            key={s.key}
                            title={s.label}
                            style={{
                              display: 'inline-block',
                              width: 8, height: 8, borderRadius: '50%',
                              background: row[s.key] ? s.color : '#E5E5EA',
                            }}
                          />
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Empty state */}
        {!loading && data && data.results.length === 0 && (
          <div className="text-center py-16 text-[#6E6E73] text-sm">
            No cell lines match <span className="text-[#1D1D1F] font-semibold">"{query}"</span>
          </div>
        )}

        {/* Initial loading */}
        {loading && !data && (
          <div className="text-center py-16 text-[#6E6E73] text-sm font-mono">Loading…</div>
        )}

        {/* ── Pagination ── */}
        {data && totalPages > 1 && (
          <div className="flex items-center justify-between mt-5">
            <div className="text-[#6E6E73] text-xs font-mono">
              {start.toLocaleString()}–{end.toLocaleString()} of {data.total.toLocaleString()}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage(p => Math.max(0, p - 1))}
                disabled={page === 0}
                className="px-4 py-2 text-sm border border-[#D2D2D7] rounded-xl text-[#1D1D1F] hover:bg-[#F5F5F7] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                ← Previous
              </button>
              <span className="px-3 text-xs text-[#6E6E73] font-mono">
                {page + 1} / {totalPages}
              </span>
              <button
                onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                className="px-4 py-2 text-sm border border-[#D2D2D7] rounded-xl text-[#1D1D1F] hover:bg-[#F5F5F7] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                Next →
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
