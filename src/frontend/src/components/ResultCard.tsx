import { useState } from 'react'
import FitRing from './FitRing'
import MetricRow from './MetricRow'
import LabelValueRow from './LabelValueRow'
import HoverPopover from './HoverPopover'
import FitScoreExplanation from './FitScoreExplanation'
import { renderBold } from '../utils/renderBold'
import { getScorePct, getSources, hasContextFilter as computeHasContextFilter, isMultiGeneResult } from '../utils/resultFields'
import { useSearch } from '../context/SearchContext'

interface Props {
  result: any
  gene: string
  diseaseFilter?: string
  excludeGenes?: string[]
  // Multi-gene combined search — passed through to /recommend/agentic so
  // the "Get AI Justification" button produces a joint justification
  // (see generate_multi_gene_justification) for a multi-gene result,
  // same as the single-gene path, just with this also set.
  additionalGenes?: string[]
  // weights_used from the API response — passed through so the per-card
  // Fit Score hover tooltip (Item 2) can show the REAL weights for this
  // query, not generic/static text. Flat dict for single-gene, {gene:
  // {...weights}} for multi-gene (same shape describeWeights expects).
  weightsUsed?: any
  onCellLineClick: (cvcl: string) => void
}

const SECTION_LABELS = [
  'RECOMMENDATION', 'KEY REASON', 'EVIDENCE SUMMARY',
  'TRADE-OFFS', 'BEST FOR', 'DATA CITATIONS',
  'DATA SOURCES', 'LITERATURE CITATIONS', 'LITERATURE',
]

const MONO_SECTIONS = new Set(['DATA SOURCES', 'LITERATURE CITATIONS', 'LITERATURE', 'DATA CITATIONS'])

// LLM output (Groq/gpt-oss-20b, observed directly) uses Unicode dash/hyphen
// lookalikes inconsistently and non-deterministically — e.g. "TRADE‑OFFS"
// with U+2011 NON-BREAKING HYPHEN instead of a plain ASCII "-" — which used
// to make parseJustification's exact .includes() match silently fail and
// swallow that section's content into whichever section matched last (see
// the multi-gene AI-justification investigation: reproduced directly by
// running this exact function against a real captured response). Not
// unique to multi-gene — a single-gene response can hit the same thing by
// chance depending on what that particular LLM call happened to generate.
// Normalizing BOTH the scanned text and SECTION_LABELS before matching
// (SECTION_LABELS is already plain ASCII today, so normalizing it is a
// no-op in practice, but doing it keeps the comparison correct even if a
// label ever changes) closes this off structurally rather than patching
// one specific character that happened to be observed.
// U+2010 HYPHEN, U+2011 NON-BREAKING HYPHEN, U+2012 FIGURE DASH,
// U+2013 EN DASH, U+2014 EM DASH — a contiguous Unicode range, written as
// escapes (not literal glyphs) so it's unambiguous to read and immune to
// any editor/encoding mangling of near-identical-looking characters.
const DASH_VARIANTS = /[‐-—]/g
const normalizeDashes = (s: string): string => s.replace(DASH_VARIANTS, '-')
const NORMALIZED_SECTION_LABELS = SECTION_LABELS.map(normalizeDashes)

function parseJustification(text: string): Record<string, string> {
  const sections: Record<string, string> = {}
  const lines = text.split('\n')
  let currentLabel = ''
  let currentContent: string[] = []

  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed) continue

    const normalizedLine = normalizeDashes(trimmed.toUpperCase())
    const matchIdx = NORMALIZED_SECTION_LABELS.findIndex(lbl => normalizedLine.includes(lbl))
    // Original (non-normalized) label is still what gets stored/looked up
    // as the section key elsewhere (SECTION_LABELS.filter(...), parsed[k],
    // etc.) — only the MATCHING comparison is dash-tolerant, not the key.
    const matchedLabel = matchIdx >= 0 ? SECTION_LABELS[matchIdx] : undefined

    if (matchedLabel) {
      if (currentLabel) sections[currentLabel] = currentContent.join(' ').trim()
      currentLabel = matchedLabel
      const afterColon = trimmed.split(':').slice(1).join(':').trim()
      currentContent = afterColon ? [afterColon] : []
    } else if (currentLabel) {
      currentContent.push(trimmed)
    }
  }

  if (currentLabel) sections[currentLabel] = currentContent.join(' ').trim()
  return sections
}

// Three-state palette (see Part 4 of the design spec) reused for evidence
// level labels (High/Medium/Low/Confirms/Contradicts), not just metric bars.
function levelColor(level: string): string {
  if (level === 'High' || level === 'Confirms') return 'var(--accent)'
  if (level === 'Medium') return 'var(--accent-amber)'
  if (level === 'Low' || level === 'Contradicts') return 'var(--muted-state)'
  return 'var(--muted-state)'
}

function Section({ label, count, children }: { label: string; count?: number; children: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border-t border-cso-border mt-3 pt-3">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1.5 text-xs text-cso-body hover:text-cso-heading transition-colors"
      >
        <span>{open ? '▾' : '▸'}</span>
        {label}
        {count !== undefined && <span className="text-cso-muted font-mono">({count})</span>}
      </button>
      {open && <div className="mt-2">{children}</div>}
    </div>
  )
}

export default function ResultCard({ result, gene, diseaseFilter, excludeGenes, additionalGenes, weightsUsed, onCellLineClick }: Props) {
  // Item 3: AI-justification state (per cell line) now lives in
  // SearchContext, keyed by cellosaurus_id, instead of local state here —
  // so clicking "Get AI Justification" (which can take well over a
  // minute for the agentic path) and navigating away no longer orphans
  // the result; it lands in state that outlives this component.
  const { agenticByCellLine, runAgenticJustification } = useSearch()
  const ai = agenticByCellLine[result.cellosaurus_id]
  const aiData = ai?.data ?? null
  const aiLoading = ai?.loading ?? false
  const aiError = ai?.error ?? false

  const isTop = result.rank === 1
  // Multi-gene combined-search results (see multi_gene_ranker.rank_multi_gene
  // / api/main.py's _build_multi_gene_result) use combined_score in place of
  // final_score, and omit essentially every other single-gene evidence
  // field (rna_score, hpa_evidence, pathway_activity_score, ...) — detected
  // here via per_gene_percentiles' presence, the one field unique to that
  // shape, so the sections below that don't apply to it stay hidden rather
  // than rendering misleading zeros. Shared with the GRID/COMPACT layouts
  // via utils/resultFields so this logic can't drift between variants.
  const isMultiGene = isMultiGeneResult(result)
  const scorePct = getScorePct(result)
  const hasContextFilter = computeHasContextFilter(diseaseFilter)
  const sources = getSources(result)

  const handleAI = () => {
    runAgenticJustification({
      gene,
      additionalGenes,
      diseaseFilter,
      excludeGenes,
      targetCellosaurusId: result.cellosaurus_id,
    })
  }

  return (
    <div className="result-card-wrap bg-cso-card border border-cso-border rounded p-5">
      {/* Top row — rank, name, CVCL id, fit ring. Part 6: the rank numeral
          and cell line name carry real visual weight, and the ring (sized
          up further, see FitRing's own default) is the clear focal point
          rather than one element among several equally-weighted ones.
          Part 5: only rank 1 keeps the ring's accent fill — see FitRing's
          `dim` prop and index.css's hover/focus restore rule; this is the
          reference's hard-binary "top result" signal, not the old
          decorative left-border stripe (removed — redundant with this). */}
      <div className="flex items-start justify-between mb-4 gap-5">
        <div className="flex items-start gap-4 flex-1 min-w-0">
          <span
            className="font-mono leading-none flex-shrink-0"
            style={{ fontSize: '2.75rem', fontWeight: 300, color: 'var(--text-body)', opacity: 0.6 }}
          >
            {String(result.rank).padStart(2, '0')}
          </span>
          <div className="min-w-0 pt-1.5">
            <button
              onClick={() => onCellLineClick(result.cellosaurus_id)}
              className="hover:underline transition-colors text-left truncate max-w-xs block"
              style={{ color: 'var(--text-heading)', fontWeight: 700, fontSize: '1.375rem', lineHeight: 1.15 }}
            >
              {result.official_name}
            </button>
            <div className="text-cso-body font-mono text-xs mt-1">{result.cellosaurus_id}</div>
          </div>
        </div>
        {/* Item 2: the Fit Score weight breakdown is now a hover/focus
            popover anchored right here, not a permanent panel above the
            results list — real per-query weights via weightsUsed, not
            static text. */}
        <HoverPopover
          content={
            <FitScoreExplanation
              genes={[gene, ...(additionalGenes ?? [])]}
              weightsUsed={weightsUsed}
              isMultiGene={isMultiGene}
              geneClass={result.gene_class}
            />
          }
        >
          <FitRing score={scorePct} label={isMultiGene ? 'COMBINED' : 'FIT SCORE'} size={96} dim={!isTop} />
        </HoverPopover>
      </div>

      {/* Per-gene percentile breakdown — multi-gene only. The transparency
          mechanism for a combined search, in place of GENE CLASS/GENE ROLE
          and the EVIDENCE metrics below (which don't apply — those fields
          don't exist on a multi-gene result). */}
      {isMultiGene && (
        <div className="text-xs text-cso-body font-mono mb-3">
          {Object.entries(result.per_gene_percentiles as Record<string, number>)
            .map(([g, pct]) => `${g}: ${Math.round(pct * 100)}%ile`)
            .join(', ')}
        </div>
      )}

      {/* GENE CLASS / GENE ROLE — explicit labelled rows (Part 1, PROBLEM A).
          Single-gene only; both fields are naturally absent on a multi-gene
          result. */}
      {!isMultiGene && (result.gene_class || result.gene_role) && (
        <div className="mb-3">
          {result.gene_class && (
            <LabelValueRow
              label="Gene class"
              value={(result.gene_class as string).replace(/_/g, '-')}
              explanation="Determines which evidence types are weighted most heavily for this gene."
            />
          )}
          {result.gene_role && (
            <LabelValueRow
              label="Gene role"
              value={result.gene_role}
              explanation="The gene's biological function, for context."
            />
          )}
        </div>
      )}

      {/* EVIDENCE — labelled metric rows with icon, hover explanation, bar,
          and value (Part 1 PROBLEM B, Part 4). Single-gene only. */}
      {!isMultiGene && (
        <div className="mb-3">
          <div className="text-[11px] uppercase tracking-[0.08em] text-cso-body mb-1.5">Evidence</div>
          <MetricRow metric="rna"     value={result.rna_score ?? 0} />
          <MetricRow metric="protein" value={result.protein_score ?? 0} />
          <MetricRow metric="quality" value={result.quality_score ?? 0} />
          <MetricRow
            metric="context"
            value={hasContextFilter ? (result.context_score ?? 0) : null}
            tooltip={hasContextFilter ? undefined : 'No disease or tissue filter was applied to this search'}
          />
          <MetricRow metric="pathway" value={result.pathway_activity_score ?? 0} />
          <MetricRow metric="rwr"     value={result.rwr_score ?? 0} />
        </div>
      )}

      {/* Source chips */}
      {sources.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          {sources.map(s => (
            <span key={s} className="text-xs border border-cso-border text-cso-body px-2 py-0.5 rounded-full">
              {s}
            </span>
          ))}
        </div>
      )}

      {/* Disease/tissue match + source count — deliberately labelled
          "DISEASE / TISSUE" rather than reusing "CONTEXT" (which the
          EVIDENCE section above already uses for the context SCORE) to
          avoid recreating the exact kind of label collision Part 1 exists
          to fix. */}
      {(result.disease || result.lineage || result.n_sources) && (
        <div className="text-cso-body text-xs mb-2">
          {[result.disease, result.lineage, result.n_sources ? `${result.n_sources} RNA src` : null]
            .filter(Boolean)
            .join(', ')}
        </div>
      )}

      {/* Doubling time */}
      {result.growth_properties?.doubling_time && (
        <div className="text-xs text-cso-body mt-1">
          Doubling time: {result.growth_properties.doubling_time.min} to{' '}
          {result.growth_properties.doubling_time.max}{' '}
          {result.growth_properties.doubling_time.unit}s
        </div>
      )}

      {/* Exclusion warnings */}
      {result.exclusion_warnings?.length > 0 && (
        <div className="mb-2 space-y-0.5">
          {result.exclusion_warnings.map((w: any, i: number) => (
            <div key={i} className="text-cso-amber text-xs">{w.message}</div>
          ))}
        </div>
      )}

      {/* Alternatives */}
      {result.alternatives?.length > 0 && (
        <Section label="Similar alternatives" count={result.alternatives.length}>
          <div className="space-y-2">
            {result.alternatives.map((alt: any, i: number) => (
              <div key={i} className="bg-cso-bg rounded p-3 text-xs">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-cso-heading font-medium">{alt.official_name}</span>
                  <span className="text-cso-heading font-mono">{Math.round((alt.similarity_score ?? 0) * 100)}%</span>
                </div>
                <div className="text-cso-body mb-1 font-mono">{alt.cellosaurus_id}</div>
                <div className="text-cso-body italic leading-relaxed">{alt.similarity_reason}</div>
                {alt.note && <div className="text-cso-body mt-1">{alt.note}</div>}
                <a
                  href={alt.cellosaurus_url ?? `https://www.cellosaurus.org/${alt.cellosaurus_id}`}
                  target="_blank" rel="noopener noreferrer"
                  className="text-cso-heading hover:underline mt-1 inline-block"
                >
                  Cellosaurus ↗
                </a>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Score breakdown — supplementary detail not already covered by the
          EVIDENCE rows above: the plain-English reasoning behind quality/
          context/pathway, per-source agreement levels, and the ranking
          comparison to the next cell line. Single-gene only. */}
      {!isMultiGene && (
      <Section label="Score breakdown">
        <div className="space-y-1.5 text-xs text-cso-body">
          {result.quality_explanation && <div>Quality: {result.quality_explanation}</div>}
          {result.context_explanation && <div>Context: {result.context_explanation}</div>}
          {result.pathway_genes_total > 0 && (
            <div>
              Pathway: {result.pathway_genes_expressed}/{result.pathway_genes_total} pathway-neighbour genes also expressed here
            </div>
          )}
        </div>

        {/* Per-source evidence — label + exact percentile, so cross-source
            agreement/disagreement is visible without losing precision to a
            coarse Low/Medium/High bucket. */}
        <div className="grid grid-cols-4 gap-3 mt-3 pt-3 border-t border-cso-border">
          {[
            { key: 'hpa_evidence', name: 'HPA RNA' },
            { key: 'depmap_evidence', name: 'DepMap' },
            { key: 'geo_evidence', name: 'GEO' },
            { key: 'protein_evidence', name: 'Proteomics' },
          ].map(({ key, name }) => {
            const ev = result[key]
            if (!ev) return null
            return (
              <div key={key} className="text-xs">
                <div className="text-cso-body">{name}</div>
                <div className="font-semibold" style={{ color: levelColor(ev.label) }}>
                  {ev.label}
                </div>
                {ev.percentile && (
                  <div className="text-[10px] text-cso-muted">
                    {ev.percentile}
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {result.vs_next_rank && (
          <div className="mt-3 pt-3 border-t border-cso-border text-xs text-cso-body italic">
            {result.vs_next_rank}
          </div>
        )}
      </Section>
      )}

      {/* AI Justification — available for both single- and multi-gene
          results. For multi-gene, handleAI() passes additionalGenes
          through to /recommend/agentic, which produces ONE joint
          justification addressing all queried genes together (see
          generate_multi_gene_justification) — not per-gene separately. */}
      <div className="border-t border-cso-border mt-3 pt-3">
        {!aiData ? (
          <button
            onClick={handleAI}
            disabled={aiLoading}
            className="flex items-center gap-2 text-xs border border-cso-border text-cso-body px-3 py-1.5 rounded hover:border-cso-heading hover:text-cso-heading transition-colors disabled:opacity-50"
          >
            {aiLoading ? (
              <>
                <span className="w-3 h-3 border border-cso-border border-t-cso-heading rounded-full animate-spin" />
                Generating AI justification…
              </>
            ) : (
              'Get AI Justification →'
            )}
          </button>
        ) : (
          <div className="space-y-3">
            {aiData.results?.[0]?.justification && (() => {
              const raw = typeof aiData.results[0].justification === 'string'
                ? aiData.results[0].justification
                : JSON.stringify(aiData.results[0].justification, null, 2)
              const parsed = parseJustification(raw)
              const mainKeys = SECTION_LABELS.filter(k => parsed[k] && !MONO_SECTIONS.has(k))
              const monoKeys = SECTION_LABELS.filter(k => parsed[k] && MONO_SECTIONS.has(k))
              const hasAny   = mainKeys.length > 0 || monoKeys.length > 0

              return hasAny ? (
                <div className="bg-cso-bg rounded p-3 space-y-2.5">
                  {mainKeys.map(k => (
                    <div key={k}>
                      <div className="text-[10px] font-semibold tracking-wider text-cso-body uppercase mb-0.5">{k}</div>
                      <p className="text-xs text-cso-heading leading-relaxed">{renderBold(parsed[k])}</p>
                    </div>
                  ))}
                  {monoKeys.map(k => (
                    <div key={k} className="border-t border-cso-border pt-2">
                      <div className="text-[10px] font-semibold tracking-wider text-cso-body uppercase mb-0.5">{k}</div>
                      <pre className="text-[10px] text-cso-body font-mono whitespace-pre-wrap leading-relaxed">{parsed[k]}</pre>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="bg-cso-bg rounded p-3 text-xs text-cso-heading leading-relaxed">{renderBold(raw)}</div>
              )
            })()}
            {aiData.dataset_citations && (
              <div className="space-y-0.5">
                {aiData.dataset_citations.map((c: any) => (
                  <div key={c.key} className="text-cso-body text-xs font-mono">[{c.key}] {c.name}</div>
                ))}
              </div>
            )}
          </div>
        )}
        {aiError && (
          <div className="text-cso-amber text-xs mt-1">
            AI justification failed, check that the Ollama server is running.
          </div>
        )}
      </div>
    </div>
  )
}
