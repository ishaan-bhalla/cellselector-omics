import { useMemo, useState } from 'react'
import { api } from '../api/client'
import SlideOver from '../components/SlideOver'
import LoadingSpinner from '../components/LoadingSpinner'

interface GNode {
  id: string
  type: 'gene' | 'pathway' | 'cell_line'
  role?: string | null
  name?: string | null
  url?: string | null
}

interface GEdge {
  source: string
  target: string
  relation: 'MEMBER_OF' | 'CONTAINS' | 'EXPRESSED_IN'
  weight?: number | null
}

interface GraphData {
  gene: string
  nodes: GNode[]
  edges: GEdge[]
  node_count: number
  edge_count: number
}

const COLORS: Record<string, string> = {
  target:   '#D97706', // amber — target gene, centre
  pathway:  '#7C3AED', // purple — middle ring
  neighbor: '#2563EB', // blue — outer ring
  cell_line:'#059669', // green
}

const RELATION_STYLE: Record<string, { stroke: string; dash?: string; label: string }> = {
  MEMBER_OF:    { stroke: '#7C3AED', label: 'MEMBER_OF (gene → pathway)' },
  CONTAINS:     { stroke: '#2563EB', dash: '3,3', label: 'CONTAINS (pathway → gene)' },
  EXPRESSED_IN: { stroke: '#059669', label: 'EXPRESSED_IN (gene → cell line)' },
}

const W = 900, H = 900, CX = W / 2, CY = H / 2
const R_PATHWAY = 190
const R_GENE = 330
const R_CELL = 430

interface Laid extends GNode {
  x: number
  y: number
  angle: number
}

function layoutGraph(nodes: GNode[], edges: GEdge[], targetGene: string): Map<string, Laid> {
  const byId = new Map(nodes.map(n => [n.id, n]))
  const childrenByRelation = (relation: string) => {
    const m = new Map<string, string[]>()
    for (const e of edges) {
      if (e.relation !== relation) continue
      if (!m.has(e.source)) m.set(e.source, [])
      m.get(e.source)!.push(e.target)
    }
    return m
  }
  const memberOf    = childrenByRelation('MEMBER_OF')
  const contains     = childrenByRelation('CONTAINS')
  const expressedIn  = childrenByRelation('EXPRESSED_IN')

  const pos = new Map<string, Laid>()
  const targetNode = byId.get(targetGene)
  if (targetNode) pos.set(targetGene, { ...targetNode, x: CX, y: CY, angle: -Math.PI / 2 })

  const pathways = memberOf.get(targetGene) ?? []
  const pathwayStep = (2 * Math.PI) / Math.max(pathways.length, 1)

  pathways.forEach((pid, i) => {
    const pNode = byId.get(pid)
    if (!pNode) return
    const angle = i * pathwayStep - Math.PI / 2
    pos.set(pid, { ...pNode, x: CX + Math.cos(angle) * R_PATHWAY, y: CY + Math.sin(angle) * R_PATHWAY, angle })

    const neighborGenes = (contains.get(pid) ?? []).filter(g => !pos.has(g))
    const sector = pathwayStep * 0.82
    const start = angle - sector / 2
    const step = neighborGenes.length > 1 ? sector / (neighborGenes.length - 1) : 0
    neighborGenes.forEach((gid, j) => {
      const gNode = byId.get(gid)
      if (!gNode) return
      const gAngle = neighborGenes.length > 1 ? start + j * step : angle
      pos.set(gid, { ...gNode, x: CX + Math.cos(gAngle) * R_GENE, y: CY + Math.sin(gAngle) * R_GENE, angle: gAngle })
    })
  })

  // Cell lines: spread around whichever gene expresses them, one ring further out
  expressedIn.forEach((cvcls, gid) => {
    const parent = pos.get(gid)
    const baseAngle = parent ? parent.angle : 0
    const unplaced = cvcls.filter(c => !pos.has(c))
    const spread = 0.55
    const start = baseAngle - spread / 2
    const step = unplaced.length > 1 ? spread / (unplaced.length - 1) : 0
    unplaced.forEach((cid, k) => {
      const cNode = byId.get(cid)
      if (!cNode) return
      const a = unplaced.length > 1 ? start + k * step : baseAngle
      pos.set(cid, { ...cNode, x: CX + Math.cos(a) * R_CELL, y: CY + Math.sin(a) * R_CELL, angle: a })
    })
  })

  return pos
}

function nodeVisual(n: GNode) {
  if (n.type === 'gene' && n.role === 'target') return { color: COLORS.target, r: 16 }
  if (n.type === 'pathway') return { color: COLORS.pathway, r: 10 }
  if (n.type === 'gene') return { color: COLORS.neighbor, r: 6 }
  return { color: COLORS.cell_line, r: 5 }
}

function nodeLabel(n: GNode): string {
  if (n.type === 'pathway') return n.name || n.id
  return n.id
}

export default function GraphExplorer() {
  const [gene, setGene] = useState('')
  const [diseaseFilter, setDiseaseFilter] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [graphData, setGraphData] = useState<GraphData | null>(null)
  const [neighbors, setNeighbors] = useState<any[] | null>(null)
  const [bestLines, setBestLines] = useState<any[] | null>(null)

  const [selected, setSelected] = useState<GNode | null>(null)
  const [hovered, setHovered] = useState<{ node: GNode; x: number; y: number } | null>(null)
  const [selectedCVCL, setSelectedCVCL] = useState<string | null>(null)

  const positions = useMemo(() => {
    if (!graphData) return null
    return layoutGraph(graphData.nodes, graphData.edges, graphData.gene)
  }, [graphData])

  const handleExplore = async () => {
    const g = gene.trim().toUpperCase()
    if (!g) return
    setLoading(true); setError(null)
    setGraphData(null); setNeighbors(null); setBestLines(null); setSelected(null)
    try {
      const [gd, nb, bl] = await Promise.all([
        api.exploreGraph(g, diseaseFilter.trim() || undefined),
        api.pathwayNeighbors(g),
        api.cellLinesViaPathway(g, diseaseFilter.trim() || undefined, 5),
      ])
      if (gd.detail) throw new Error(gd.detail)
      setGraphData(gd)
      setNeighbors(nb.neighbors ?? [])
      setBestLines(bl.results ?? [])
    } catch (e: any) {
      setError(e?.message ?? 'Request failed. Is the API running on port 8001?')
    } finally {
      setLoading(false)
    }
  }

  const onNodeClick = (n: GNode) => {
    if (n.type === 'cell_line') { setSelectedCVCL(n.id); return }
    setSelected(n)
  }

  const inputCls = 'w-full bg-white border border-[#D2D2D7] text-[#1D1D1F] px-4 py-2.5 rounded-xl text-sm focus:outline-none focus:border-[#1D1D1F] transition-colors placeholder-[#D2D2D7]'

  return (
    <div className="min-h-screen bg-white pt-24">
      {/* Header / controls */}
      <div className="bg-white border-b border-[#D2D2D7]">
        <div className="max-w-3xl mx-auto px-6 pb-8">
          <p className="text-[#6E6E73] text-xs tracking-[0.2em] uppercase mb-2">Knowledge Graph</p>
          <h1 className="text-[#1D1D1F] text-3xl font-bold mb-8">Graph Explorer</h1>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">
            <div>
              <label className="text-[#6E6E73] text-xs uppercase tracking-widest block mb-2">Gene Name</label>
              <input
                type="text"
                value={gene}
                onChange={e => setGene(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleExplore()}
                placeholder="e.g. EGFR, KRAS, BRAF"
                autoFocus
                className="w-full bg-white border border-[#D2D2D7] text-[#1D1D1F] font-mono text-lg px-4 py-3 rounded-xl focus:outline-none focus:border-[#1D1D1F] transition-colors placeholder-[#D2D2D7]"
              />
            </div>
            <div>
              <label className="text-[#6E6E73] text-xs uppercase tracking-widest block mb-2">Disease Filter (optional)</label>
              <input
                type="text"
                value={diseaseFilter}
                onChange={e => setDiseaseFilter(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleExplore()}
                placeholder="e.g. lung, breast"
                className={inputCls}
                style={{ marginTop: 2 }}
              />
            </div>
          </div>

          <button
            onClick={handleExplore}
            disabled={!gene.trim() || loading}
            className="w-full bg-[#1D1D1F] text-white font-semibold py-3 rounded-xl hover:bg-[#333333] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading ? 'Exploring…' : 'Explore Graph →'}
          </button>
          <p className="text-[#6E6E73] text-xs mt-3">
            Queries a persistent gene → pathway → gene → cell-line graph in Neo4j (KEGG + expression
            data, pre-ingested — try genes like EGFR, KRAS, BRAF, TP53, ERBB2). A gene not yet ingested
            will return an empty graph rather than fetching live.
          </p>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-8">
        {loading && (
          <div className="flex justify-center py-24">
            <LoadingSpinner text="Building knowledge graph — querying KEGG pathways, resolving neighbor genes, scoring expression…" />
          </div>
        )}

        {error && (
          <div className="bg-[#FCE4EC] border border-[#F8BBD9] rounded-xl p-4 text-[#C62828] text-sm mb-6">
            {error}
          </div>
        )}

        {!graphData && !loading && !error && (
          <div className="text-center py-24">
            <div className="text-[#D2D2D7] text-6xl mb-5">⬡</div>
            <div className="text-[#6E6E73] text-sm">
              Enter a gene symbol above and press{' '}
              <span className="text-[#1D1D1F] font-semibold">Explore Graph</span>
            </div>
          </div>
        )}

        {graphData && positions && !loading && (
          <>
            {/* Graph canvas */}
            <div className="border border-[#D2D2D7] rounded-2xl overflow-hidden bg-[#FAFAFA] mb-4 relative">
              <svg
                viewBox={`0 0 ${W} ${H}`}
                className="w-full h-auto"
                style={{ maxHeight: 640, display: 'block' }}
              >
                {/* Edges */}
                {graphData.edges.map((e, i) => {
                  const a = positions.get(e.source)
                  const b = positions.get(e.target)
                  if (!a || !b) return null
                  const style = RELATION_STYLE[e.relation]
                  const opacity = e.relation === 'EXPRESSED_IN'
                    ? 0.25 + Math.min(1, Math.max(0, e.weight ?? 0)) * 0.5
                    : 0.45
                  return (
                    <line
                      key={i}
                      x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                      stroke={style.stroke}
                      strokeWidth={e.relation === 'MEMBER_OF' ? 1.6 : 1}
                      strokeDasharray={style.dash}
                      opacity={opacity}
                    />
                  )
                })}

                {/* Nodes */}
                {Array.from(positions.values()).map(n => {
                  const { color, r } = nodeVisual(n)
                  const isSelected = selected?.id === n.id
                  return (
                    <g
                      key={n.id}
                      transform={`translate(${n.x.toFixed(1)}, ${n.y.toFixed(1)})`}
                      style={{ cursor: 'pointer' }}
                      onClick={() => onNodeClick(n)}
                      onMouseEnter={() => setHovered({ node: n, x: n.x, y: n.y })}
                      onMouseLeave={() => setHovered(null)}
                    >
                      <circle
                        r={r}
                        fill={color}
                        stroke={isSelected ? '#1D1D1F' : 'white'}
                        strokeWidth={isSelected ? 2.5 : 1.5}
                      />
                      {(n.type !== 'cell_line') && (
                        <text
                          x={0} y={r + 12}
                          textAnchor="middle"
                          fontSize={n.role === 'target' ? 13 : 10}
                          fontWeight={n.role === 'target' ? 700 : 500}
                          fontFamily="ui-monospace, monospace"
                          fill="#1D1D1F"
                          style={{ pointerEvents: 'none' }}
                        >
                          {n.type === 'pathway' ? '' : nodeLabel(n)}
                        </text>
                      )}
                    </g>
                  )
                })}
              </svg>

              {/* Tooltip */}
              {hovered && (
                <div
                  className="absolute bg-[#1D1D1F] text-white text-xs rounded-lg px-3 py-2 pointer-events-none"
                  style={{
                    left: `${(hovered.x / W) * 100}%`,
                    top: `${(hovered.y / H) * 100}%`,
                    transform: 'translate(-50%, -130%)',
                    whiteSpace: 'nowrap',
                    zIndex: 10,
                  }}
                >
                  <div className="font-semibold">{nodeLabel(hovered.node)}</div>
                  <div className="text-[#A1A1AA]">
                    {hovered.node.type}{hovered.node.role ? ` · ${hovered.node.role}` : ''}
                  </div>
                </div>
              )}

              {/* Legend — purely informational; pointer-events-none so it never
                  blocks clicks on graph nodes that happen to render underneath it */}
              <div className="absolute top-4 right-4 bg-white/90 backdrop-blur border border-[#D2D2D7] rounded-xl p-3 text-xs space-y-2 pointer-events-none" style={{ minWidth: 190 }}>
                <div className="text-[#6E6E73] uppercase tracking-widest text-[10px] mb-1">Nodes</div>
                {[
                  ['Target gene', COLORS.target],
                  ['Pathway', COLORS.pathway],
                  ['Neighbor gene', COLORS.neighbor],
                  ['Cell line', COLORS.cell_line],
                ].map(([label, color]) => (
                  <div key={label} className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: color as string }} />
                    <span className="text-[#1D1D1F]">{label}</span>
                  </div>
                ))}
                <div className="text-[#6E6E73] uppercase tracking-widest text-[10px] mt-3 mb-1">Edges</div>
                {Object.values(RELATION_STYLE).map(s => (
                  <div key={s.label} className="flex items-center gap-2">
                    <span className="w-4 h-0" style={{ borderTop: `2px ${s.dash ? 'dashed' : 'solid'} ${s.stroke}` }} />
                    <span className="text-[#1D1D1F]">{s.label}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Selected node detail panel (gene / pathway) */}
            {selected && (
              <div className="border border-[#D2D2D7] rounded-xl p-4 mb-8 flex items-start justify-between">
                <div>
                  <div className="text-[#6E6E73] text-xs uppercase tracking-widest mb-1">
                    {selected.type === 'pathway' ? 'Pathway' : 'Gene'}
                    {selected.role === 'target' ? ' · target' : selected.role === 'pathway_neighbor' ? ' · pathway neighbor' : ''}
                  </div>
                  <div className="text-[#1D1D1F] font-bold font-mono">
                    {selected.type === 'pathway' ? selected.name : selected.id}
                  </div>
                  {selected.type === 'pathway' && (
                    <div className="text-[#6E6E73] text-xs font-mono mt-0.5">{selected.id}</div>
                  )}
                  {selected.url && (
                    <a href={selected.url} target="_blank" rel="noopener noreferrer"
                       className="text-xs text-[#2563EB] hover:underline mt-1 inline-block">
                      View on KEGG ↗
                    </a>
                  )}
                </div>
                <button onClick={() => setSelected(null)} className="text-[#6E6E73] hover:text-[#1D1D1F] text-sm">✕</button>
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              {/* Pathway neighbor genes */}
              <div>
                <h2 className="text-[#1D1D1F] font-bold text-lg mb-1">Pathway Neighbor Genes</h2>
                <p className="text-[#6E6E73] text-xs mb-4">
                  Genes sharing ≥1 KEGG pathway with {graphData.gene} — a genuine 2-hop graph query.
                </p>
                {neighbors && neighbors.length > 0 ? (
                  <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
                    {neighbors.map(n => (
                      <div key={n.gene} className="border border-[#D2D2D7] rounded-lg px-3 py-2 flex items-center justify-between">
                        <span className="font-mono text-sm text-[#1D1D1F]">{n.gene}</span>
                        <span className="text-[#6E6E73] text-xs" title={n.shared_pathways.map((p: any) => p.pathway_name).join(', ')}>
                          {n.shared_pathways.length} shared pathway{n.shared_pathways.length === 1 ? '' : 's'}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-[#6E6E73] text-sm">No pathway neighbors found.</div>
                )}
              </div>

              {/* Best cell lines via pathway */}
              <div>
                <h2 className="text-[#1D1D1F] font-bold text-lg mb-1">Best Cell Lines</h2>
                <p className="text-[#6E6E73] text-xs mb-4">Direct target-gene matches + pathway-connected matches.</p>
                {bestLines && bestLines.length > 0 ? (
                  <div className="space-y-2">
                    {bestLines.map(b => {
                      const direct = b.connecting_genes.find((g: any) => g.is_target)
                      return (
                        <div key={b.cellosaurus_id}
                             className="border border-[#D2D2D7] rounded-lg px-3 py-2 cursor-pointer hover:border-[#1D1D1F] transition-colors"
                             onClick={() => setSelectedCVCL(b.cellosaurus_id)}>
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-[#1D1D1F] text-sm font-semibold">{b.official_name}</span>
                            <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase tracking-wide ${direct ? 'bg-[#FEF3C7] text-[#92400E]' : 'bg-[#DBEAFE] text-[#1E40AF]'}`}>
                              {direct ? 'Direct' : 'Pathway-connected'}
                            </span>
                          </div>
                          <div className="text-[#6E6E73] text-xs font-mono">
                            {b.connecting_genes.map((g: any) => g.gene).join(', ')} · score {b.max_score.toFixed(2)}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                ) : (
                  <div className="text-[#6E6E73] text-sm">No connected cell lines found.</div>
                )}
              </div>
            </div>
          </>
        )}
      </div>

      {selectedCVCL && (
        <SlideOver cellosaurus_id={selectedCVCL} onClose={() => setSelectedCVCL(null)} />
      )}
    </div>
  )
}
