import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import DNAHelix from '../components/DNAHelix'
import Reveal from '../components/Reveal'

// Underline-reveal CTA — a thin bar that grows from 0 to full width under
// the text on hover (transform: scaleX, transform-origin left), in place
// of a filled pill button. Local hover state rather than a global CSS
// rule, so this stays self-contained.
function UnderlineCTA({ to, children }: { to: string; children: React.ReactNode }) {
  const [hovered, setHovered] = useState(false)
  return (
    <Link
      to={to}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        position: 'relative', color: 'var(--text-heading)',
        fontSize: 18, fontWeight: 600, textDecoration: 'none',
        paddingBottom: 6, display: 'inline-block',
      }}
    >
      {children}
      <span
        aria-hidden="true"
        style={{
          position: 'absolute', left: 0, right: 0, bottom: 0, height: 2,
          background: 'var(--accent)', transform: hovered ? 'scaleX(1)' : 'scaleX(0)',
          transformOrigin: 'left', transition: 'transform 280ms ease',
        }}
      />
    </Link>
  )
}

// Real, verifiable capabilities — kept from the Phase 1 copy, restyled
// below as a flowing list (no bordered 3-card row, no numbered-circle step
// tracker — see Part 1's explicit redesign instruction).
const CAPABILITIES = [
  {
    n: '01',
    title: 'Multi-omics integration',
    body: 'RNA expression from HPA and DepMap, protein abundance from CCLE proteomics, and CRISPR dependency from DepMap, combined into one evidence-backed score.',
  },
  {
    n: '02',
    title: 'Gene-class-adaptive scoring',
    body: 'Weights are learned separately for tissue-specific, ubiquitous, and loss-of-function genes, since each is suited by a different mix of evidence.',
  },
  {
    n: '03',
    title: 'Knowledge-graph network centrality',
    body: 'A random-walk-with-restart signal over a graph of genes, cell lines, and pathways captures network proximity that direct expression data alone misses.',
  },
  {
    n: '04',
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

// Doubled/ghost headline — the front copy solid, a second copy of the same
// text rendered behind it at low opacity and a small offset (Part 1's
// "documenting emotion, documenting emotion" device). Pure CSS: one
// relatively-positioned element, one absolutely-positioned duplicate
// behind it — no library, no JS-driven animation.
function KineticHeadline() {
  const text = (
    <>
      Find the right<br />cell line.
    </>
  )
  return (
    <div style={{ position: 'relative' }}>
      <h1
        aria-hidden="true"
        style={{
          position: 'absolute', top: 10, left: 8,
          margin: 0, color: 'var(--text-heading)', opacity: 0.1,
          fontSize: 'clamp(3.5rem, 9vw, 8.5rem)', fontWeight: 700, lineHeight: 0.98,
          letterSpacing: '-0.02em', userSelect: 'none', pointerEvents: 'none',
        }}
      >
        {text}
      </h1>
      <h1
        style={{
          position: 'relative', margin: 0, color: 'var(--text-heading)',
          fontSize: 'clamp(3.5rem, 9vw, 8.5rem)', fontWeight: 700, lineHeight: 0.98,
          letterSpacing: '-0.02em',
        }}
      >
        {text}
      </h1>
    </div>
  )
}

export default function Home() {
  const [mousePos, setMousePos] = useState<{ x: number; y: number } | null>(null)
  const [health, setHealth] = useState<any>(null)

  useEffect(() => {
    api.health().then(setHealth).catch(() => {})
  }, [])

  const statItems = [
    { value: health?.cell_lines ? health.cell_lines.toLocaleString() : '2,076', label: 'Cell lines' },
    { value: '5',  label: 'Data sources' },
    { value: '44', label: 'Validated genes' },
    { value: '3',  label: 'Gene classes' },
  ]

  return (
    <div className="bg-cso-bg">

      {/* ── Hero — immersive, full-bleed, chrome-free: eyebrow, oversized
          doubled headline, subhead, one confident CTA. DNAHelix demoted to
          a faint full-bleed backdrop rather than a competing 55%-width
          zone, so the typography is unambiguously the focal point. ── */}
      <section
        style={{
          position: 'relative', height: 'calc(100vh - 65px)', minHeight: 560,
          overflow: 'hidden', background: 'var(--bg)',
          display: 'flex', flexDirection: 'column', justifyContent: 'center',
        }}
        onMouseMove={e => {
          const r = e.currentTarget.getBoundingClientRect()
          setMousePos({ x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height })
        }}
        onMouseLeave={() => setMousePos(null)}
      >
        {/* Backdrop layer — full-bleed, faint, behind the text */}
        <div style={{ position: 'absolute', inset: 0, opacity: 0.28, pointerEvents: 'none' }}>
          <DNAHelix mousePos={mousePos} />
        </div>

        {/* Content — left-aligned, generous side margin, vertically centred */}
        <div style={{ position: 'relative', zIndex: 1, padding: '0 5vw', maxWidth: 1100 }}>
          <p style={{
            fontFamily: "'IBM Plex Mono', monospace", color: 'var(--text-body)',
            fontSize: 11, letterSpacing: '0.15em', textTransform: 'uppercase',
            marginBottom: 28,
          }}>
            University of Bristol &times; AstraZeneca
          </p>

          <KineticHeadline />

          <p style={{ color: 'var(--text-body)', fontSize: 18, lineHeight: 1.6, maxWidth: 460, margin: '32px 0 0' }}>
            Multi-omics recommendation across 2,076 human cell lines,
            evidence-backed and citable.
          </p>

          <div style={{ display: 'flex', alignItems: 'center', gap: 40, marginTop: 48 }}>
            {/* Primary CTA — underline-reveal, not a filled pill button */}
            <UnderlineCTA to="/search">Launch Tool</UnderlineCTA>
            <Link
              to="/about"
              style={{ color: 'var(--text-body)', fontSize: 14, textDecoration: 'none' }}
            >
              About the project
            </Link>
          </div>
        </div>

        {/* Scroll cue — a thin line with a slow single fade pulse, no bounce */}
        <div
          className="absolute bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2"
          style={{ pointerEvents: 'none' }}
        >
          <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-cso-body scroll-pulse">Scroll</span>
          <div className="scroll-pulse" style={{ width: 1, height: 28, background: 'var(--border)' }} />
        </div>
      </section>

      {/* ── Details — one flowing section (stats, capabilities, steps),
          no bordered 3-card grid, no numbered-circle step tracker. Each
          block reveals on scroll (Part 2). ── */}
      <section className="bg-cso-bg" style={{ borderTop: '1px solid var(--border)' }}>
        <div className="max-w-4xl mx-auto px-6 py-28">

          {/* Stats — quiet, inline, mono */}
          <Reveal className="mb-28">
            <div className="flex flex-wrap gap-x-12 gap-y-4" style={{ borderBottom: '1px solid var(--border)', paddingBottom: 40 }}>
              {statItems.map(s => (
                <div key={s.label}>
                  <div className="font-mono font-bold tabular-nums" style={{ fontSize: 'clamp(2rem, 4vw, 3rem)', color: 'var(--text-heading)', lineHeight: 1 }}>
                    {s.value}
                  </div>
                  <div className="text-[11px] uppercase tracking-[0.1em] text-cso-body mt-2">{s.label}</div>
                </div>
              ))}
            </div>
          </Reveal>

          {/* Capabilities — flowing list, large index numerals, not cards */}
          <div className="mb-28">
            <Reveal>
              <h2 className="font-bold mb-14" style={{ fontSize: 'clamp(1.75rem, 3vw, 2.5rem)', color: 'var(--text-heading)', letterSpacing: '-0.01em' }}>
                What it does
              </h2>
            </Reveal>
            <div>
              {CAPABILITIES.map((c, i) => (
                <Reveal key={c.n} delay={i * 60}>
                  <div
                    className="flex items-baseline gap-8 py-8"
                    style={{ borderTop: '1px solid var(--border)' }}
                  >
                    <span className="font-mono flex-shrink-0" style={{ fontSize: '1.1rem', color: 'var(--accent)' }}>
                      {c.n}
                    </span>
                    <div>
                      <h3 className="font-semibold mb-2" style={{ fontSize: '1.25rem', color: 'var(--text-heading)' }}>
                        {c.title}
                      </h3>
                      <p className="text-cso-body leading-relaxed" style={{ fontSize: 15, maxWidth: 560 }}>{c.body}</p>
                    </div>
                  </div>
                </Reveal>
              ))}
            </div>
          </div>

          {/* Steps — compact, de-emphasised inline flow, no numbered circles */}
          <Reveal>
            <h2 className="font-bold mb-10" style={{ fontSize: 'clamp(1.75rem, 3vw, 2.5rem)', color: 'var(--text-heading)', letterSpacing: '-0.01em' }}>
              How to use it
            </h2>
          </Reveal>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8">
            {STEPS.map((step, i) => (
              <Reveal key={step.n} delay={i * 60}>
                <div className="font-mono text-xs mb-2" style={{ color: 'var(--accent)' }}>{step.n}</div>
                <p className="font-semibold mb-1" style={{ fontSize: 15, color: 'var(--text-heading)' }}>{step.title}</p>
                <p className="text-cso-body text-xs leading-relaxed">{step.body}</p>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="bg-cso-bg py-8" style={{ borderTop: '1px solid var(--border)' }}>
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
