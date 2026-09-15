import Reveal from '../components/Reveal'

const PRINCIPLES = [
  {
    n: '01',
    title: 'Multi-omics, not single-source',
    body: 'RNA expression (HPA, DepMap), protein abundance (CCLE proteomics), and CRISPR dependency are combined rather than relying on any one dataset, with GEO expression used as an independent cross-check.',
  },
  {
    n: '02',
    title: 'Gene-class-adaptive scoring',
    body: 'A tissue-specific oncogene, a ubiquitously expressed control gene, and a loss-of-function tumour suppressor are suited by different evidence. Weights are learned separately for each class rather than applying one formula to every gene.',
  },
  {
    n: '03',
    title: 'Network context, not just direct evidence',
    body: 'A knowledge graph of genes, cell lines and pathways adds a network-centrality signal (random walk with restart) alongside direct expression and mutation evidence, surfacing candidates a purely tabular lookup would miss.',
  },
  {
    n: '04',
    title: 'Evidence-backed, not black-box',
    body: 'Every score decomposes into its component parts, and an optional agentic justification cites the specific datasets behind its recommendation, so a result can be checked rather than taken on faith.',
  },
]

export default function About() {
  return (
    <div className="bg-cso-bg">
      <section className="bg-cso-card py-24" style={{ borderBottom: '1px solid var(--border)' }}>
        <div className="max-w-4xl mx-auto px-6">
          <Reveal>
            <p className="text-[11px] uppercase tracking-[0.08em] text-cso-body mb-4">About</p>
            <h1
              className="font-bold mb-8"
              style={{ fontSize: 'clamp(2.5rem, 6vw, 4.5rem)', color: 'var(--text-heading)', lineHeight: 1.02, letterSpacing: '-0.02em' }}
            >
              A multi-omics cell<br />line recommender
            </h1>
            <p className="text-cso-body leading-relaxed mb-5" style={{ fontSize: 19, maxWidth: 640 }}>
              CellSelector Omics ranks candidate human cell lines for a gene of
              interest by combining RNA expression, protein abundance, CRISPR
              dependency, mutation status and knowledge-graph network
              centrality into a single, evidence-backed Fit Score.
            </p>
            <p className="text-cso-body leading-relaxed" style={{ fontSize: 19, maxWidth: 640 }}>
              It's an MSc group project run jointly by the University of
              Bristol and AstraZeneca, aimed at the everyday question a
              researcher faces before an experiment even starts: which of
              thousands of candidate cell lines actually suits the gene, and
              why.
            </p>
          </Reveal>
        </div>
      </section>

      <section className="bg-cso-bg py-24">
        <div className="max-w-4xl mx-auto px-6">
          <Reveal>
            <h2 className="font-bold mb-14" style={{ fontSize: 'clamp(1.75rem, 3.5vw, 2.75rem)', color: 'var(--text-heading)', letterSpacing: '-0.01em' }}>
              How it works
            </h2>
          </Reveal>
          <div>
            {PRINCIPLES.map((p, i) => (
              <Reveal key={p.n} delay={i * 60}>
                <div className="flex items-baseline gap-8 py-8" style={{ borderTop: '1px solid var(--border)' }}>
                  <span className="font-mono flex-shrink-0" style={{ fontSize: '1.1rem', color: 'var(--text-body)' }}>{p.n}</span>
                  <div>
                    <h3 className="font-semibold mb-2" style={{ fontSize: '1.25rem', color: 'var(--text-heading)' }}>{p.title}</h3>
                    <p className="text-cso-body leading-relaxed" style={{ fontSize: 15, maxWidth: 560 }}>{p.body}</p>
                  </div>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-cso-card py-24" style={{ borderTop: '1px solid var(--border)' }}>
        <div className="max-w-4xl mx-auto px-6">
          <Reveal>
            <h2 className="font-bold mb-8" style={{ fontSize: 'clamp(1.75rem, 3.5vw, 2.75rem)', color: 'var(--text-heading)', letterSpacing: '-0.01em' }}>
              Scope
            </h2>
            <p className="text-cso-body leading-relaxed mb-4" style={{ fontSize: 16, maxWidth: 640 }}>
              The tool covers a fixed panel of human cell lines drawn from
              DepMap, HPA, GEO and CCLE, mapped to Cellosaurus identifiers so
              every result is traceable back to a canonical, citable record.
              Scoring weights are class-adaptive rather than gene-specific,
              learned once against a validation set of literature-confirmed
              gene, cell line associations and checked with cross-validation
              before being deployed.
            </p>
            <p className="text-cso-body leading-relaxed" style={{ fontSize: 16, maxWidth: 640 }}>
              It does not replace domain expertise. It narrows a large search
              space to a short, evidence-ranked list, with the reasoning
              behind every rank visible rather than hidden inside a single
              opaque score.
            </p>
          </Reveal>
        </div>
      </section>
    </div>
  )
}
