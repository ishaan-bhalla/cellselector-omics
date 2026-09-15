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
    <div className="bg-cso-bg pt-24">
      <section className="bg-cso-card py-20">
        <div className="max-w-4xl mx-auto px-6">
          <p className="text-[11px] uppercase tracking-[0.08em] text-cso-body mb-3">About</p>
          <h1 className="text-cso-heading text-4xl font-bold mb-6">
            A multi-omics cell line recommender
          </h1>
          <p className="text-cso-body text-lg leading-relaxed mb-5">
            CellSelector Omics ranks candidate human cell lines for a gene of
            interest by combining RNA expression, protein abundance, CRISPR
            dependency, mutation status and knowledge-graph network
            centrality into a single, evidence-backed Fit Score.
          </p>
          <p className="text-cso-body text-lg leading-relaxed">
            It's an MSc group project run jointly by the University of
            Bristol and AstraZeneca, aimed at the everyday question a
            researcher faces before an experiment even starts: which of
            thousands of candidate cell lines actually suits the gene, and
            why.
          </p>
        </div>
      </section>

      <section className="bg-cso-bg py-16">
        <div className="max-w-4xl mx-auto px-6">
          <h2 className="text-cso-heading text-2xl font-bold mb-10">How it works</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            {PRINCIPLES.map(p => (
              <div key={p.n} className="bg-cso-card border border-cso-border rounded p-6">
                <div className="font-mono text-xs text-cso-teal mb-3">{p.n}</div>
                <h3 className="text-cso-heading font-semibold text-base mb-2">{p.title}</h3>
                <p className="text-cso-body text-sm leading-relaxed">{p.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-cso-card py-16">
        <div className="max-w-4xl mx-auto px-6">
          <h2 className="text-cso-heading text-2xl font-bold mb-6">Scope</h2>
          <p className="text-cso-body text-base leading-relaxed mb-4">
            The tool covers a fixed panel of human cell lines drawn from
            DepMap, HPA, GEO and CCLE, mapped to Cellosaurus identifiers so
            every result is traceable back to a canonical, citable record.
            Scoring weights are class-adaptive rather than gene-specific,
            learned once against a validation set of literature-confirmed
            gene, cell line associations and checked with cross-validation
            before being deployed.
          </p>
          <p className="text-cso-body text-base leading-relaxed">
            It does not replace domain expertise. It narrows a large search
            space to a short, evidence-ranked list, with the reasoning
            behind every rank visible rather than hidden inside a single
            opaque score.
          </p>
        </div>
      </section>
    </div>
  )
}
