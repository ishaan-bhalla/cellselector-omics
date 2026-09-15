import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { api } from '../api/client'
import { loadSearchResults, saveSearchResults } from '../utils/searchState'

// Item 3 — lifts the classical-search AND per-card agentic-justification
// fetch lifecycle out of Search.tsx / ResultCard.tsx (which unmount on
// navigation) into a provider mounted once at the App level (see
// App.tsx), so an in-flight request is no longer tied to the lifetime of
// the component that started it.
//
// The earlier (pre-Item-3) bug wasn't that navigating away literally
// aborted the fetch — a bare `await fetch(...)` isn't cancelled by a
// React unmount unless something wires an AbortController to a cleanup
// effect, which this code never did. The real problem was that the
// fetch's RESULT was orphaned: `setLoading`/`setAllResults` targeted
// Search.tsx's own local state, which React had already thrown away by
// the time the request resolved, so the update landed nowhere and a
// fresh Search mount on return showed nothing. Moving the state itself
// (not just the trigger) up here fixes that at the root — the state
// this fetch resolves into now lives exactly as long as the app does.
//
// LOADING_LINES lives here (not Search.tsx) because the staged-reveal
// interval driving `loadLine` must keep advancing while Search is
// unmounted too, for the takeover to resume at the right stage on
// return — Search.tsx imports it back for display. "Analysis complete"
// was removed as a displayed line entirely (Item 4) — seeing the results
// IS the completion signal now, nothing needs to state it, and the
// interval simply holds on the last real line until the fetch resolves.
export const LOADING_LINES = [
  'Resolving gene symbol',
  'Computing RNA expression scores',
  'Applying protein expression weights',
  'Running GEO cross-validation',
  'Ranking 2,076 cell lines',
  'Computing similarity alternatives',
]

export interface ClassicalSearchParams {
  gene: string
  additionalGenes: string[]
  diseaseFilter?: string
  excludeGenes: string[]
}

interface ClassicalSearchState {
  loading: boolean
  error: string | null
  results: any | null
  loadLine: number
}

export interface AgenticParams {
  gene: string
  additionalGenes?: string[]
  diseaseFilter?: string
  excludeGenes?: string[]
  targetCellosaurusId: string
}

interface AgenticState {
  loading: boolean
  error: boolean
  data: any | null
}

interface SearchContextValue {
  classical: ClassicalSearchState
  runClassicalSearch: (params: ClassicalSearchParams) => Promise<void>
  // Keyed by cellosaurus_id so multiple cards' "Get AI Justification"
  // requests can be in flight independently, each surviving navigation
  // the same way the main search does.
  agenticByCellLine: Record<string, AgenticState>
  runAgenticJustification: (params: AgenticParams) => Promise<void>
}

const SearchContext = createContext<SearchContextValue | null>(null)

export function SearchProvider({ children }: { children: ReactNode }) {
  // Seeded from sessionStorage once on provider mount (which happens once
  // per app session, at App.tsx — not per Search.tsx visit), same initial
  // values Search.tsx used to seed its own local state with directly.
  const [results, setResults] = useState<any | null>(() => loadSearchResults())
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loadLine, setLoadLine] = useState(0)
  const [agenticByCellLine, setAgenticByCellLine] = useState<Record<string, AgenticState>>({})

  // Drives the staged console-line reveal independent of whether Search
  // is currently mounted — see the module docstring above.
  useEffect(() => {
    if (!loading) { setLoadLine(0); return }
    const id = setInterval(() => setLoadLine(l => Math.min(l + 1, LOADING_LINES.length - 1)), 650)
    return () => clearInterval(id)
  }, [loading])

  // Item 6's sessionStorage results-persistence now lives here (moved out
  // of Search.tsx) rather than being duplicated in both places — see the
  // "don't leave two competing persistence mechanisms" note in the task.
  // Search.tsx's OWN sessionStorage effect still covers the draft form
  // fields (gene typed so far, filters, etc.) — a genuinely different
  // concern (what you're about to search) from this (what you last
  // searched and got back), so both coexist without conflicting.
  useEffect(() => {
    saveSearchResults(results)
  }, [results])

  // Guards a genuine race: if a second search starts before the first
  // resolves, only the LATEST call's result should ever be committed.
  const requestIdRef = useRef(0)

  const runClassicalSearch = async (params: ClassicalSearchParams) => {
    const thisRequestId = ++requestIdRef.current
    setLoading(true)
    setError(null)
    try {
      const r = await api.recommendClassical({
        gene: params.gene,
        additional_genes: params.additionalGenes,
        disease_filter: params.diseaseFilter,
        exclude_genes: params.excludeGenes.length ? params.excludeGenes : undefined,
        top_n: 20,
      })
      if (thisRequestId !== requestIdRef.current) return // superseded by a newer search
      if (r.detail) throw new Error(r.detail)
      setResults(r)
    } catch (e: any) {
      if (thisRequestId !== requestIdRef.current) return
      setError(e?.message ?? 'Request failed. Is the API running on port 8001?')
    } finally {
      if (thisRequestId === requestIdRef.current) setLoading(false)
    }
  }

  const runAgenticJustification = async (params: AgenticParams) => {
    const cvcl = params.targetCellosaurusId
    setAgenticByCellLine(prev => ({ ...prev, [cvcl]: { loading: true, error: false, data: null } }))
    try {
      const data = await api.recommendAgentic({
        gene: params.gene,
        additional_genes: params.additionalGenes,
        disease_filter: params.diseaseFilter,
        exclude_genes: params.excludeGenes,
        target_cellosaurus_id: cvcl,
        top_n: 1,
      })
      setAgenticByCellLine(prev => ({ ...prev, [cvcl]: { loading: false, error: false, data } }))
    } catch {
      setAgenticByCellLine(prev => ({ ...prev, [cvcl]: { loading: false, error: true, data: null } }))
    }
  }

  return (
    <SearchContext.Provider
      value={{
        classical: { loading, error, results, loadLine },
        runClassicalSearch,
        agenticByCellLine,
        runAgenticJustification,
      }}
    >
      {children}
    </SearchContext.Provider>
  )
}

export function useSearch(): SearchContextValue {
  const ctx = useContext(SearchContext)
  if (!ctx) throw new Error('useSearch must be used within a SearchProvider')
  return ctx
}
