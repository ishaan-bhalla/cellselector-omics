import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import DNAHelix from '../components/DNAHelix'

// Real, verifiable capabilities — not a three-card row (prohibited by the
// design system), a 2x2 grid instead.
const CAPABILITIES = [
  {
    title: 'Multi-omics integration',
    body: 'RNA expression from HPA and DepMap, protein abundance from CCLE proteomics, and CRISPR dependency from DepMap, combined into one evidence-backed score.',
  },
  {
    title: 'Gene-class-adaptive scoring',
    body: 'Weights are learned separately for tissue-specific, ubiquitous, and loss-of-function genes, since each is suited by a different mix of evidence.',
  },
  {
    title: 'Knowledge-graph network centrality',
    body: 'A random-walk-with-restart signal over a graph of genes, cell lines, and pathways captures network proximity that direct expression data alone misses.',
  },
  {
    title: 'Agentic justifications with citations',
    body: 'An optional AI-generated rationale explains a recommendation in plain language and cites the specific datasets behind it, so it can be checked, not just trusted.',
  },
]

const STEPS = [
  { n: '01', title: 'Enter a gene symbol', body: 'e.g. EGFR, BRCA1, KIT' },
  { n: '02', title: 'Set optional filters', body: 'disease, tissue, or genes to exclude' },
  { n: '03', title: 'Review ranked cell lines', body: 'with a full evidence breakdown per candidate' },
  { n: '04', title: 'Get an AI justification', body: 'a cited, plain-language rationale for the top pick' },
]

export default function Home() {
  const [mousePos, setMousePos] = useState<{ x: number; y: number } | null>(null)
  const [health, setHealth] = useState<any>(null)

  useEffect(() => {
    api.health().then(setHealth).catch(() => {})
  }, [])

  // Real, verifiable figures only (no invented statistics) — the cell line
  // count comes live from /health with a hardcoded fallback matching its
  // known current value; the other three are structural facts about the
  // scoring system itself, not results that could go stale.
  const statItems = [
    { value: health?.cell_lines ? health.cell_lines.toLocaleString() : '2,076', label: 'Cell lines' },
    { value: '5',  label: 'Data sources' },
    { value: '44', label: 'Validated genes' },
    { value: '3',  label: 'Gene classes' },
  ]

  return (
    <div className="bg-cso-bg">

      {/* ── Hero ── */}
      <section style={{ position: 'relative', height: 'calc(100vh - 65px)', minHeight: 480, overflow: 'hidden', background: 'var(--bg)' }}>

        {/* Zone 1 — DNA helix, left 55% */}
        <div
          style={{ position: 'absolute', left: 0, top: 0, width: '55%', height: '100%', overflow: 'hidden' }}
          onMouseMove={e => {
            const r = e.currentTarget.getBoundingClientRect()
            setMousePos({ x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height })
          }}
          onMouseLeave={() => setMousePos(null)}
        >
          <DNAHelix mousePos={mousePos} />
        </div>

        {/* Thin fade divider */}
        <div
          style={{
            position: 'absolute', left: '55%', top: '10%',
            height: '80%', width: 1, pointerEvents: 'none',
            background: 'linear-gradient(to bottom, transparent, var(--border) 20%, var(--border) 80%, transparent)',
          }}
        />

        {/* Zone 2 — text, right 45%, vertically centered */}
        <div
          style={{
            position: 'absolute', right: 0, top: 0,
            width: '45%', height: '100%',
            display: 'flex', flexDirection: 'column', justifyContent: 'center',
            padding: '0 60px 0 40px',
            background: 'var(--bg)',
          }}
        >
          <p style={{
            fontFamily: "'IBM Plex Mono', monospace", color: 'var(--text-body)',
            fontSize: 11, letterSpacing: '0.15em', textTransform: 'uppercase',
            marginBottom: 24,
          }}>
            University of Bristol &times; AstraZeneca
          </p>
          <h1 style={{ color: 'var(--text-heading)', fontSize: 56, fontWeight: 700, lineHeight: 1.1, marginBottom: 20 }}>
            Find the right<br />cell line.
          </h1>
          <p style={{ color: 'var(--text-body)', fontSize: 17, lineHeight: 1.6, maxWidth: 380, marginBottom: 40 }}>
            Multi-omics recommendation across 2,076 human cell lines,
            evidence-backed and citable.
          </p>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <Link
              to="/search"
              style={{
                background: 'var(--accent)', color: 'var(--bg-card)',
                borderRadius: 4, padding: '13px 26px',
                fontWeight: 600, fontSize: 14,
                textDecoration: 'none', display: 'inline-block',
              }}
            >
              Launch tool
            </Link>
            <Link
              to="/about"
              style={{
                background: 'transparent', border: '1px solid var(--border)',
                color: 'var(--text-heading)', borderRadius: 4, padding: '13px 26px',
                fontSize: 14, textDecoration: 'none', display: 'inline-block',
              }}
            >
              About
            </Link>
          </div>
        </div>

        {/* Scroll indicator — custom SVG chevron, not a unicode glyph (the
            previous "↓ SCROLL" text character was the reported rendering
            glitch at the top of the stats band immediately below). */}
        <div
          className="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-1.5 z-10"
          style={{ pointerEvents: 'none' }}
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="var(--text-body)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M3 6l5 5 5-5" />
          </svg>
          <span className="text-[10px] font-mono uppercase tracking-[0.15em] text-cso-body">Scroll</span>
        </div>
      </section>

      {/* ── Stats ── */}
      <section className="bg-cso-card py-14" style={{ borderTop: '1px solid var(--border)', borderBottom: '1px solid var(--border)' }}>
        <div className="max-w-5xl mx-auto px-6">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-8">
            {statItems.map(s => (
              <div key={s.label} className="text-center">
                <div className="text-cso-heading font-mono font-bold text-3xl mb-1 tabular-nums">
                  {s.value}
                </div>
                <div className="text-[11px] uppercase tracking-[0.08em] text-cso-body">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Capabilities (2x2, not three-in-a-row) ── */}
      <section className="bg-cso-bg py-20">
        <div className="max-w-5xl mx-auto px-6">
          <h2 className="text-cso-heading text-3xl font-bold mb-12 text-center">What it does</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            {CAPABILITIES.map(c => (
              <div key={c.title} className="bg-cso-card border border-cso-border rounded p-7">
                <h3 className="text-cso-heading font-semibold text-lg mb-2.5">{c.title}</h3>
                <p className="text-cso-body text-sm leading-relaxed">{c.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Steps ── */}
      <section className="bg-cso-card py-20" style={{ borderTop: '1px solid var(--border)', borderBottom: '1px solid var(--border)' }}>
        <div className="max-w-5xl mx-auto px-6">
          <h2 className="text-cso-heading text-3xl font-bold mb-12 text-center">How to use it</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8">
            {STEPS.map(step => (
              <div key={step.n}>
                <div className="font-mono text-xs text-cso-teal mb-3">{step.n}</div>
                <p className="text-cso-heading text-sm font-semibold mb-1">{step.title}</p>
                <p className="text-cso-body text-xs leading-relaxed">{step.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="bg-cso-bg py-8">
        <div className="max-w-5xl mx-auto px-6 flex flex-col sm:flex-row justify-between items-center gap-3">
          <div className="text-cso-body text-xs">
            CellSelector Omics, University of Bristol &times; AstraZeneca, MSc Group Project 2026
          </div>
          <div className="text-cso-body font-mono text-xs">v1.0</div>
        </div>
      </footer>
    </div>
  )
}
