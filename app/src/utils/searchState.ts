// Item 6 — persists Search page state across navigation (Search -> Home/
// About/Data -> Search) via sessionStorage, per-session working state
// rather than a permanent preference (that distinction is why this uses
// sessionStorage and not localStorage, unlike theme.ts/viewMode.ts).
//
// Split into two keys, written by two separate effects in Search.tsx:
// FORM_KEY (gene/additionalGenes/diseaseFilter/excludeGenes/topN) updates
// on every keystroke, so it stays small and cheap to re-serialize;
// RESULTS_KEY (the last-fetched allResults blob, which can be much
// larger) only updates when a search actually completes, not per
// keystroke of an unrelated field.

const FORM_KEY = 'cso-search-form'
const RESULTS_KEY = 'cso-search-results'

export interface SearchFormState {
  gene: string
  additionalGenes: string[]
  diseaseFilter: string
  excludeGenes: string[]
  topN: number
}

export function loadSearchForm(): Partial<SearchFormState> {
  try {
    const raw = sessionStorage.getItem(FORM_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

export function saveSearchForm(state: SearchFormState): void {
  try {
    sessionStorage.setItem(FORM_KEY, JSON.stringify(state))
  } catch {
    // Private browsing / storage disabled / quota exceeded — this is a
    // convenience feature, not worth surfacing an error for; the form
    // just won't persist this time.
  }
}

export function loadSearchResults(): any | null {
  try {
    const raw = sessionStorage.getItem(RESULTS_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function saveSearchResults(results: any | null): void {
  try {
    if (results) sessionStorage.setItem(RESULTS_KEY, JSON.stringify(results))
    else sessionStorage.removeItem(RESULTS_KEY)
  } catch {
    // Same reasoning as saveSearchForm.
  }
}
