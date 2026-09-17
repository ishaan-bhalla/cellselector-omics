import { useEffect, useMemo, useRef, useState } from 'react'

// Generic client-side-filtered dropdown input — the same component behind
// the primary gene field, the additional-gene field, the Exclude Genes
// picker, and now the Disease Filter (see Search.tsx). Fully controlled
// (value/onChange/onSelect owned by the caller) so each use site can
// decide its own select behaviour (replace the value in place for the
// primary gene/disease filter, or append-and-clear for a multi-select
// chip picker) without this component needing to know which one it is.
// Originally named GeneAutocompleteInput; generalised (options, not
// allGenes) once Disease Filter needed the identical pattern rather than
// a second, duplicated implementation.
interface Props {
  value: string
  onChange: (v: string) => void
  onSelect: (v: string) => void
  options: string[]
  excludeFromSuggestions?: string[]
  placeholder?: string
  autoFocus?: boolean
  /** Default false (gene symbols): matches on a case-insensitive prefix.
   *  Disease names aren't typed in a consistent case/prefix convention by
   *  users, so Disease Filter passes true for a substring match instead. */
  matchAnywhere?: boolean
  className?: string
  /** 'lg' (default) matches the primary/additional gene fields' prominent
   *  size; 'sm' matches the smaller filter-row inputs (Disease Filter,
   *  Exclude Genes) — a real prop rather than a one-off className hack,
   *  since this component is now used in both visual contexts. */
  size?: 'sm' | 'lg'
}

export default function AutocompleteInput({
  value,
  onChange,
  onSelect,
  options,
  excludeFromSuggestions = [],
  placeholder,
  autoFocus,
  matchAnywhere = false,
  className,
  size = 'lg',
}: Props) {
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
    const q = value.trim().toLowerCase()
    if (!q) return []
    return options
      .filter(o => (matchAnywhere ? o.toLowerCase().includes(q) : o.toUpperCase().startsWith(q.toUpperCase())))
      .filter(o => !excludeFromSuggestions.includes(o))
      .slice(0, 10)
  }, [value, options, excludeFromSuggestions, matchAnywhere])

  return (
    <div className={`relative ${className ?? ''}`} ref={wrapRef}>
      <input
        type="text"
        value={value}
        onChange={e => { onChange(e.target.value); setShowDropdown(true) }}
        onFocus={() => value.trim() && setShowDropdown(true)}
        placeholder={placeholder}
        autoFocus={autoFocus}
        autoComplete="off"
        className={
          size === 'lg'
            ? 'w-full h-full bg-cso-card border border-[var(--border)] text-[var(--text-heading)] font-mono text-lg px-4 py-3 rounded focus:outline-none focus:border-[var(--text-heading)] transition-colors placeholder-[var(--muted-state)]'
            : 'w-full h-full bg-cso-card border border-[var(--border)] text-[var(--text-heading)] text-sm px-4 py-2.5 rounded focus:outline-none focus:border-[var(--text-heading)] transition-colors placeholder-[var(--border)]'
        }
      />
      {showDropdown && suggestions.length > 0 && (
        <div className="absolute left-0 right-0 z-20 mt-1 max-h-64 overflow-y-auto bg-cso-card border border-[var(--border)] rounded">
          {suggestions.map(o => (
            <button
              key={o}
              type="button"
              onClick={() => { onSelect(o); setShowDropdown(false) }}
              className="w-full text-left px-4 py-2 font-mono text-sm text-[var(--text-heading)] hover:bg-[var(--bg)] transition-colors"
            >
              {o}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
