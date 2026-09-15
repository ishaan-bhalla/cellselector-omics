import Reveal from '../components/Reveal'

const SOURCES = [
  {
    key: 'HPA',
    name: 'Human Protein Atlas',
    body: 'RNA expression (nTPM) across the human cell line panel, used as one of two primary transcript-abundance signals.',
  },
  {
    key: 'DepMap',
    name: 'DepMap (Broad Institute)',
    body: 'RNA expression (log1p TPM) and CRISPR gene-essentiality (dependency) scores, drawn from the same cell line collection.',
  },
  {
    key: 'GEO',
    name: 'Gene Expression Omnibus',
    body: 'An independent RNA expression source, used as a confirmatory cross-check against HPA and DepMap rather than a primary ranking input.',
  },
  {
    key: 'CCLE',
    name: 'CCLE Proteomics',
    body: 'Mass-spectrometry protein abundance, the primary protein-level signal alongside the RNA sources above.',
  },
  {
    key: 'Neo4j',
    name: 'Knowledge graph',
    body: 'Genes, cell lines, pathways and mutation records linked in a graph database, powering pathway-neighbour and network-centrality (RWR) scoring.',
  },
]

export default function Data() {
  return (
    <div className="bg-cso-bg">
      <section className="bg-cso-card py-24" style={{ borderBottom: '1px solid var(--border)' }}>
        <div className="max-w-4xl mx-auto px-6">
          <Reveal>
            <p className="text-[11px] uppercase tracking-[0.08em] text-cso-body mb-4">Data</p>
            <h1
              className="font-bold mb-8"
              style={{ fontSize: 'clamp(2.5rem, 6vw, 4.5rem)', color: 'var(--text-heading)', lineHeight: 1.02, letterSpacing: '-0.02em' }}
            >
              Underlying datasets
            </h1>
            <p className="text-cso-body leading-relaxed" style={{ fontSize: 19, maxWidth: 640 }}>
              Every Fit Score is built from five independently sourced datasets,
              combined via a gene-class-adaptive weighted formula and a graph
              database of gene, cell line and pathway relationships. No
              component is invented or estimated: a missing data source for a
              given gene or cell line lowers that component's weight rather
              than being filled in with a guess.
            </p>
          </Reveal>
        </div>
      </section>

      <section className="bg-cso-bg py-24">
        <div className="max-w-4xl mx-auto px-6">
          <Reveal>
            <h2 className="font-bold mb-12" style={{ fontSize: 'clamp(1.75rem, 3.5vw, 2.75rem)', color: 'var(--text-heading)', letterSpacing: '-0.01em' }}>
              Sources
            </h2>
          </Reveal>
          <div>
            {SOURCES.map((s, i) => (
              <Reveal key={s.key} delay={i * 50}>
                <div className="flex items-baseline gap-6 py-6" style={{ borderTop: '1px solid var(--border)' }}>
                  <span className="text-cso-heading font-mono font-semibold text-sm flex-shrink-0 w-16">{s.key}</span>
                  <div>
                    <div className="text-cso-heading font-semibold mb-1" style={{ fontSize: '1.05rem' }}>{s.name}</div>
                    <p className="text-cso-body text-sm leading-relaxed" style={{ maxWidth: 560 }}>{s.body}</p>
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
              Validation
            </h2>
            <p className="text-cso-body leading-relaxed mb-4" style={{ fontSize: 16, maxWidth: 640 }}>
              Scoring weights are learned per gene class (tissue-specific,
              ubiquitous, loss-of-function) by maximising Mean Reciprocal Rank
              against a 44-gene validation set of literature-confirmed
              gene, cell line associations, then checked with leave-one-out
              cross-validation so a weight vector can't simply overfit the
              genes it was tuned on.
            </p>
            <p className="text-cso-body leading-relaxed" style={{ fontSize: 16, maxWidth: 640 }}>
              Candidate scoring components are only adopted into production
              once they pass the same cycle: a weight-value grid search,
              an in-sample evaluation, cross-validated re-evaluation, and a
              paired bootstrap significance test against the current
              baseline. A component that doesn't clear that bar (graph
              network centrality did; pathway-neighbour co-expression did
              not) is left out of the active formula rather than included
              for its own sake.
            </p>
          </Reveal>
        </div>
      </section>
    </div>
  )
}
