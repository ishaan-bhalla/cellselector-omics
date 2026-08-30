import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config import CELL_LINE_LOOKUP
from models.agentic.pathways import get_cached_pathway_genes, get_kegg_pathways
from models.classical.scorer import classify_gene, load_mappings, score_rna_expression
from models.classical.weights_learned import VALIDATION_SET
from models.graph.neo4j_client import run_query

# ─────────────────────────────────────────────────────────────────────────────
# One-time (or periodically re-run) ETL: populate Neo4j with gene / pathway /
# cell-line nodes for the validation gene set. NOT called per API request —
# api/main.py's /graph/* endpoints only read what's already here.
# ─────────────────────────────────────────────────────────────────────────────

_LOOKUP       = pd.read_parquet(CELL_LINE_LOOKUP, columns=["cellosaurus_id", "disease", "lineage"])
_DISEASE_MAP  = dict(zip(_LOOKUP["cellosaurus_id"], _LOOKUP["disease"]))
_LINEAGE_MAP  = dict(zip(_LOOKUP["cellosaurus_id"], _LOOKUP["lineage"]))


def _lookup(m: dict, cvcl: str) -> str:
    v = m.get(cvcl)
    return v if isinstance(v, str) and v else ""


def _ingest_expression_edges(gene: str, hpa_to_cvcl: dict, gsm_to_cvcl: dict, max_cell_lines: int) -> None:
    """Score gene's RNA expression and MERGE EXPRESSED_IN edges to its top cell lines."""
    gene_class = classify_gene(gene)
    rna = score_rna_expression(gene, hpa_to_cvcl, gsm_to_cvcl, gene_class=gene_class)
    if len(rna) == 0:
        return

    top = rna.nlargest(max_cell_lines, "rna_score")
    rows = [
        {
            "cvcl":    row["cellosaurus_id"],
            "score":   float(row["rna_score"]),
            "disease": _lookup(_DISEASE_MAP, row["cellosaurus_id"]),
            "lineage": _lookup(_LINEAGE_MAP, row["cellosaurus_id"]),
        }
        for _, row in top.iterrows()
    ]
    run_query(
        """
        UNWIND $rows AS row
        MERGE (c:CellLine {cellosaurus_id: row.cvcl})
        SET c.disease = row.disease, c.lineage = row.lineage
        WITH c, row
        MATCH (g:Gene {symbol: $gene})
        MERGE (g)-[r:EXPRESSED_IN]->(c)
        SET r.score = row.score
        """,
        {"rows": rows, "gene": gene},
    )


def ingest_gene(
    gene: str,
    hpa_to_cvcl: dict,
    gsm_to_cvcl: dict,
    scored_genes: set[str],
    max_pathways: int = 3,
    max_neighbor_genes: int = 15,
    max_cell_lines_per_gene: int = 10,
    max_cell_lines_per_neighbor: int = 3,
) -> None:
    """
    Ingest one gene: its own node + expression edges, its KEGG pathways, and
    each pathway's neighbor genes — WITH their own expression edges too.
    (Neighbor genes need expression data of their own, or
    query_best_cell_lines_via_pathway would never find a pathway-connected
    cell line for any gene outside the validation set.)

    scored_genes tracks which genes have already had RNA expression scored
    and written in this run, so a gene that shows up as a neighbor under
    multiple target genes' pathways (common — pathways overlap heavily)
    only gets scored once.
    """
    print(f"Ingesting {gene}...")

    run_query("MERGE (g:Gene {symbol: $symbol})", {"symbol": gene})

    if gene not in scored_genes:
        try:
            _ingest_expression_edges(gene, hpa_to_cvcl, gsm_to_cvcl, max_cell_lines_per_gene)
        except Exception as exc:
            print(f"  [warning] expression scoring failed for {gene}: {exc}")
        scored_genes.add(gene)

    try:
        pathways = get_kegg_pathways(gene)
        for pathway in pathways[:max_pathways]:
            pid, pname, purl = pathway["id"], pathway["name"], pathway["url"]

            run_query(
                """
                MERGE (p:Pathway {pathway_id: $pid})
                SET p.name = $pname, p.url = $purl
                WITH p
                MATCH (g:Gene {symbol: $gene})
                MERGE (g)-[:MEMBER_OF]->(p)
                """,
                {"pid": pid, "pname": pname, "purl": purl, "gene": gene},
            )

            neighbor_genes = [
                n for n in get_cached_pathway_genes(pid)[:max_neighbor_genes] if n != gene
            ]
            if not neighbor_genes:
                continue

            run_query(
                """
                UNWIND $neighbor_genes AS ngene
                MERGE (ng:Gene {symbol: ngene})
                WITH ng
                MATCH (p:Pathway {pathway_id: $pid})
                MERGE (p)-[:CONTAINS]->(ng)
                """,
                {"neighbor_genes": neighbor_genes, "pid": pid},
            )

            for ngene in neighbor_genes:
                if ngene in scored_genes:
                    continue
                try:
                    _ingest_expression_edges(
                        ngene, hpa_to_cvcl, gsm_to_cvcl, max_cell_lines_per_neighbor
                    )
                except Exception as exc:
                    print(f"  [warning] expression scoring failed for neighbor {ngene}: {exc}")
                scored_genes.add(ngene)
    except Exception as exc:
        print(f"  [warning] pathway ingestion failed for {gene}: {exc}")

    print(f"  Done: {gene}")


def ingest_all() -> None:
    genes = sorted(VALIDATION_SET.keys())
    print(f"Ingesting {len(genes)} genes into Neo4j...")

    hpa_to_cvcl, ach_to_cvcl, gsm_to_cvcl = load_mappings()
    scored_genes: set[str] = set()

    t0 = time.time()
    for i, gene in enumerate(genes, 1):
        print(f"[{i}/{len(genes)}]  (elapsed {time.time() - t0:.0f}s, {len(scored_genes)} genes scored so far)")
        ingest_gene(gene, hpa_to_cvcl, gsm_to_cvcl, scored_genes)
        time.sleep(0.5)  # courtesy pause between genes

    print(f"Ingestion complete in {time.time() - t0:.0f}s. Unique genes scored: {len(scored_genes)}")


if __name__ == "__main__":
    ingest_all()
