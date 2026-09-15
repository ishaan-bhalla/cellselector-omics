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
    <div className="bg-cso-bg pt-24">
      <section className="bg-cso-card py-20">
        <div className="max-w-4xl mx-auto px-6">
          <p className="text-[11px] uppercase tracking-[0.08em] text-cso-body mb-3">Data</p>
          <h1 className="text-cso-heading text-4xl font-bold mb-6">Underlying datasets</h1>
          <p className="text-cso-body text-lg leading-relaxed">
            Every Fit Score is built from five independently sourced datasets,
            combined via a gene-class-adaptive weighted formula and a graph
            database of gene, cell line and pathway relationships. No
            component is invented or estimated: a missing data source for a
            given gene or cell line lowers that component's weight rather
            than being filled in with a guess.
          </p>
        </div>
      </section>

      <section className="bg-cso-bg py-16">
        <div className="max-w-4xl mx-auto px-6">
          <h2 className="text-cso-heading text-2xl font-bold mb-8">Sources</h2>
          <div className="space-y-4">
            {SOURCES.map(s => (
              <div key={s.key} className="bg-cso-card border border-cso-border rounded p-5">
                <div className="flex items-baseline gap-3 mb-1.5">
                  <span className="text-cso-teal font-mono font-semibold text-xs">{s.key}</span>
                  <span className="text-cso-heading font-semibold text-sm">{s.name}</span>
                </div>
                <p className="text-cso-body text-sm leading-relaxed">{s.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-cso-card py-16">
        <div className="max-w-4xl mx-auto px-6">
          <h2 className="text-cso-heading text-2xl font-bold mb-6">Validation</h2>
          <p className="text-cso-body text-base leading-relaxed mb-4">
            Scoring weights are learned per gene class (tissue-specific,
            ubiquitous, loss-of-function) by maximising Mean Reciprocal Rank
            against a 44-gene validation set of literature-confirmed
            gene, cell line associations, then checked with leave-one-out
            cross-validation so a weight vector can't simply overfit the
            genes it was tuned on.
          </p>
          <p className="text-cso-body text-base leading-relaxed">
            Candidate scoring components are only adopted into production
            once they pass the same cycle: a weight-value grid search,
            an in-sample evaluation, cross-validated re-evaluation, and a
            paired bootstrap significance test against the current
            baseline. A component that doesn't clear that bar (graph
            network centrality did; pathway-neighbour co-expression did
            not) is left out of the active formula rather than included
            for its own sake.
          </p>
        </div>
      </section>
    </div>
  )
}
