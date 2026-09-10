from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config import (
    CELL_LINE_LOOKUP,
    DATASET_CITATIONS,
    GEO_INFO,
    MASTER_MERGED,
    PARQUET_DIR,
    SAMPLE_INFO,
)
from models.agentic.growth_properties import format_growth_properties, get_growth_properties
from models.agentic.pubmed import format_citations, get_cell_line_literature
from models.classical.scorer import get_gene_role

_PATHWAY_CACHE: dict = {}


def _get_cached_pathways(gene: str) -> list[dict]:
    if gene not in _PATHWAY_CACHE:
        from models.agentic.pathways import get_kegg_pathways
        _PATHWAY_CACHE[gene] = get_kegg_pathways(gene)
    return _PATHWAY_CACHE[gene]


def retrieve_evidence(
    gene: str,
    cellosaurus_id: str,
    top_result_df_row,
) -> dict:
    """
    Retrieve all available evidence for one (gene, cell line) pair.

    top_result_df_row: a row from rank() output (Series or dict) that already
    carries the pre-computed scores — avoids re-ranking.

    Returns a dict structured for LLM consumption.
    """
    # ── ID lookups ────────────────────────────────────────────────────────────
    lkp = pd.read_parquet(
        CELL_LINE_LOOKUP,
        columns=["cellosaurus_id", "hpa_name", "official_name",
                 "disease", "lineage"],
    )
    cell_row = lkp[lkp["cellosaurus_id"] == cellosaurus_id]
    hpa_name = (
        cell_row["hpa_name"].values[0]
        if len(cell_row) > 0 and pd.notna(cell_row["hpa_name"].values[0])
        else None
    )

    samp = pd.read_csv(SAMPLE_INFO, usecols=["DepMap_ID", "RRID"], low_memory=False)
    ach_ids = samp[samp["RRID"] == cellosaurus_id]["DepMap_ID"].tolist()

    geo_info = pd.read_csv(
        GEO_INFO, sep="\t",
        usecols=["Geo_accession", "Cellosaurus_ID"],
        low_memory=False,
    )
    gsms_for_cell = geo_info[
        geo_info["Cellosaurus_ID"] == cellosaurus_id
    ]["Geo_accession"].tolist()

    # ── 1. HPA expression ────────────────────────────────────────────────────
    hpa_evidence: dict = {}
    if hpa_name:
        hpa_raw = pd.read_parquet(
            PARQUET_DIR / "gene_expr_hpa_preprocessed.parquet",
            filters=[("gene_symbol", "=", gene), ("units", "=", "nTPM")],
            columns=["original_id", "expression_value"],
        )
        hpa_cell = hpa_raw[hpa_raw["original_id"] == hpa_name]
        if len(hpa_cell) > 0:
            val = float(hpa_cell["expression_value"].mean())
            hpa_evidence = {
                "value_ntpm":  val,
                "percentile":  round(float(top_result_df_row.get("hpa_score", 0) or 0) * 100, 1),
                "expressed":   val > 1.0,
            }

    # ── 2. DepMap expression ─────────────────────────────────────────────────
    dep_evidence: dict = {}
    dep_raw = pd.read_parquet(
        PARQUET_DIR / "gene_expr_depmap_preprocessed.parquet",
        filters=[("gene_symbol", "=", gene), ("cellosaurus_id", "=", cellosaurus_id)],
        columns=["expression_value"],
    )
    if len(dep_raw) > 0:
        val = float(dep_raw["expression_value"].mean())
        dep_evidence = {
            "value_tpm_log1p": val,
            "percentile":      round(float(top_result_df_row.get("depmap_score", 0) or 0) * 100, 1),
            "expressed":       val > 0.5,
        }

    # ── 3. GEO evidence ──────────────────────────────────────────────────────
    geo_evidence: dict = {}
    if gsms_for_cell:
        geo_raw = pd.read_parquet(
            PARQUET_DIR / "gene_expr_geo_preprocessed.parquet",
            filters=[("gene_symbol", "=", gene)],
            columns=["original_id", "expression_value"],
        )
        geo_cell = geo_raw[geo_raw["original_id"].isin(gsms_for_cell)]
        if len(geo_cell) > 0:
            vals = geo_cell["expression_value"].values.astype(float)
            median = float(np.median(vals))
            std    = float(np.std(vals))
            cv     = std / abs(median) if abs(median) > 1e-9 else float("inf")
            consistency = "high" if cv < 0.2 else ("medium" if cv < 0.5 else "low")
            geo_evidence = {
                "n_samples":   len(vals),
                "median":      round(median, 3),
                "cv":          round(min(cv, 99.0), 3),
                "consistency": consistency,
                "expressed":   median > 0,
            }

    # ── 4. Proteomics ────────────────────────────────────────────────────────
    prot_evidence: dict = {}
    if ach_ids:
        prot_raw = pd.read_parquet(
            PARQUET_DIR / "gene_expr_ccle_proteomics_preprocessed.parquet",
            filters=[("gene_symbol", "=", gene)],
            columns=["original_id", "expression_value"],
        )
        prot_cell = prot_raw[prot_raw["original_id"].isin(ach_ids)]
        if len(prot_cell) > 0:
            prot_evidence = {
                "value":      round(float(prot_cell["expression_value"].mean()), 4),
                "percentile": round(float(top_result_df_row.get("protein_score", 0) or 0) * 100, 1),
            }

    # ── 5. CRISPR dependency (essentiality — distinct from expression) ──────
    # rank() already merges score_crispr_dependency() onto every result row,
    # so dependency_score / dependency_percentile are read straight off
    # top_result_df_row rather than re-querying the parquet file here.
    crispr_dep_score = top_result_df_row.get("dependency_score")
    crispr_dep_pct   = top_result_df_row.get("dependency_percentile")
    crispr_evidence: dict | None = (
        {"score": float(crispr_dep_score), "percentile": float(crispr_dep_pct)}
        if pd.notna(crispr_dep_score) and pd.notna(crispr_dep_pct)
        else None
    )

    # ── 5b. Mutation status (PRIMARY signal for loss-of-function genes) ─────
    # rank() merges score_mutation_impact() onto every result row, so
    # mutation_impact_score / mutation_detail are read straight off the row
    # (same reuse pattern as CRISPR dependency above — no re-query).
    mut_score  = top_result_df_row.get("mutation_impact_score")
    mut_detail = top_result_df_row.get("mutation_detail")
    mutation_evidence: dict | None = (
        {
            "impact_score": round(float(mut_score), 4),
            "detail":       str(mut_detail),
        }
        if pd.notna(mut_score) and float(mut_score or 0) > 0 and mut_detail
        else None
    )

    # ── 6. Cell line metadata ────────────────────────────────────────────────
    master_cols = [
        "cellosaurus_id", "official_name", "evidence_count",
        "has_mutations", "has_fusions", "MSIScore", "Ploidy",
    ]
    master = pd.read_parquet(MASTER_MERGED, columns=master_cols)
    m_row  = master[master["cellosaurus_id"] == cellosaurus_id]

    metadata: dict = {
        "cellosaurus_id": cellosaurus_id,
        "official_name":  str(top_result_df_row.get("official_name") or cellosaurus_id),
        "disease":        str(top_result_df_row.get("disease") or "unknown"),
        "lineage":        str(top_result_df_row.get("lineage") or "unknown"),
    }
    if len(m_row) > 0:
        r = m_row.iloc[0]
        metadata.update({
            "evidence_count": int(r.get("evidence_count", 0) or 0),
            "has_mutations":  bool(r.get("has_mutations", False)),
            "has_fusions":    bool(r.get("has_fusions", False)),
            "msi_score":      round(float(r["MSIScore"]), 3) if pd.notna(r.get("MSIScore")) else None,
            "ploidy":         round(float(r["Ploidy"]), 2)   if pd.notna(r.get("Ploidy"))  else None,
        })

    # ── 7. Score breakdown ───────────────────────────────────────────────────
    def _f(key: str) -> float:
        return round(float(top_result_df_row.get(key) or 0), 4)

    scores = {
        "rna_score":             _f("rna_score"),
        "hpa_score":             _f("hpa_score"),
        "depmap_score":          _f("depmap_score"),
        "protein_score":         _f("protein_score"),
        "quality_score":         _f("quality_score"),
        "context_score":         _f("context_score"),
        "mutation_impact_score": _f("mutation_impact_score"),
        "geo_confirmation":      _f("geo_confirmation"),
        "final_score":           _f("final_score"),
    }

    # ── 8. PubMed literature ─────────────────────────────────────────────────
    cell_line_name = str(top_result_df_row.get("official_name") or cellosaurus_id)
    disease_str    = str(top_result_df_row.get("disease") or "") or None
    papers = get_cell_line_literature(gene, cell_line_name, disease_str)

    # ── 9. Dataset citations ──────────────────────────────────────────────────
    # Attach a citation for each data source that contributed evidence for
    # this cell line. Cellosaurus is always included as the ID spine.
    dataset_cites: list[dict] = []
    if hpa_evidence:
        dataset_cites.append(DATASET_CITATIONS["HPA_RNA"])
    if dep_evidence:
        dataset_cites.append(DATASET_CITATIONS["DepMap_TPM"])
    if geo_evidence:
        dataset_cites.append(DATASET_CITATIONS["GEO_expression"])
    if prot_evidence:
        dataset_cites.append(DATASET_CITATIONS["CCLE_proteomics"])
    dataset_cites.append(DATASET_CITATIONS["Cellosaurus"])

    return {
        "gene":                  gene,
        "cellosaurus_id":        cellosaurus_id,
        "hpa_expression":        hpa_evidence,
        "depmap_expression":     dep_evidence,
        "geo_expression":        geo_evidence,
        "proteomics":            prot_evidence,
        "crispr_dependency":     crispr_evidence,
        "mutation":              mutation_evidence,
        # Precise {label, score, percentile} dicts computed once in rank()
        # (see ranker.add_rank_comparisons's neighbors) and read straight
        # off top_result_df_row — same reuse pattern as crispr_dependency
        # above, no re-querying. Distinct from hpa_expression/depmap_expression/
        # geo_expression/proteomics above, which carry raw values (nTPM,
        # TPM_log1p, GEO sample stats); these carry the label+percentile
        # pair so format_context() can cite exact percentiles.
        "hpa_evidence":          top_result_df_row.get("hpa_evidence"),
        "depmap_evidence":       top_result_df_row.get("depmap_evidence"),
        "geo_evidence":          top_result_df_row.get("geo_evidence"),
        "protein_evidence":      top_result_df_row.get("protein_evidence"),
        "metadata":              metadata,
        "scores":                scores,
        "literature":            papers,
        "literature_formatted":  format_citations(papers),
        "dataset_citations":     dataset_cites,
        "pathways":              _get_cached_pathways(gene),
        "gene_role":             get_gene_role(gene),
        "growth_properties":     get_growth_properties(cellosaurus_id),
    }


def format_context(gene: str, evidence: dict) -> str:
    """
    Format retrieved evidence as a structured prompt context string for the LLM.
    """
    meta   = evidence["metadata"]
    scores = evidence["scores"]
    hpa    = evidence.get("hpa_expression", {})
    dep    = evidence.get("depmap_expression", {})
    geo    = evidence.get("geo_expression", {})
    prot   = evidence.get("proteomics", {})

    def _pct(d: dict, key: str = "percentile") -> str:
        v = d.get(key)
        return f"{v:.0f}th" if v is not None else "N/A"

    def _val(d: dict, key: str, fmt: str = ".2f") -> str:
        v = d.get(key)
        return format(v, fmt) if v is not None else "not available"

    hpa_line = (
        f"{_val(hpa, 'value_ntpm')} nTPM — {_pct(hpa)} percentile"
        if hpa else "not available"
    )
    dep_line = (
        f"{_val(dep, 'value_tpm_log1p')} TPM_log1p — {_pct(dep)} percentile"
        if dep else "not available"
    )
    if geo:
        geo_line = (
            f"{geo['n_samples']} experiments, "
            f"median={geo['median']:.2f}, "
            f"consistency={geo['consistency']} (CV={geo['cv']:.2f})"
        )
    else:
        geo_line = "not available"

    prot_line = (
        f"{_val(prot, 'value', '.4f')} — {_pct(prot)} percentile"
        if prot else "not available"
    )

    crispr = evidence.get("crispr_dependency")
    if crispr:
        crispr_score = crispr["score"]
        crispr_pct   = crispr["percentile"] * 100
        crispr_line = (
            f"Dependency score: {crispr_score:.3f} ({crispr_pct:.0f}th percentile) - "
            f"indicates how essential {gene} is for this cell line's survival, "
            f"DIFFERENT from expression level."
        )
    else:
        crispr_line = "No CRISPR dependency data available for this cell line."
    crispr_section = (
        f"CRISPR ESSENTIALITY (DepMap):\n"
        f"{crispr_line}\n"
        f"Note: high essentiality with low expression may indicate a "
        f"unique/hidden dependency worth investigating; high expression "
        f"with low essentiality suggests the gene is dispensable here "
        f"despite being transcribed."
    )

    mutation = evidence.get("mutation")
    if mutation:
        mutation_section = (
            "MUTATION STATUS (DepMap somatic variant calls):\n"
            f"- {mutation['detail']}\n"
            f"- Mutation impact score: {mutation['impact_score']:.2f}  "
            f"(0-1; combines hotspot / predicted loss-of-function / clinical "
            f"significance / AlphaMissense+REVEL evidence, worst variant wins)\n"
            f"- For a loss-of-function target this is the PRIMARY reason a line "
            f"is a relevant model — a damaging {gene} mutation, not expression "
            f"level, is what scientists select on. Cite the specific protein "
            f"change above in your justification."
        )
    else:
        mutation_section = (
            "MUTATION STATUS (DepMap somatic variant calls):\n"
            f"- No damaging {gene} variant called in this cell line — it is "
            f"most likely {gene} wild-type. For a loss-of-function target that "
            f"makes this line a CONTROL, not a disease model."
        )

    geo_conf = scores["geo_confirmation"]
    geo_conf_str = (
        "GEO CONFIRMS (+0.10 bonus)"  if geo_conf > 0 else
        "GEO CONTRADICTS (-0.10 penalty)" if geo_conf < 0 else
        "no GEO data (neutral)"
    )

    lit_formatted = evidence.get("literature_formatted", "SUPPORTING LITERATURE:\n  (no relevant papers found)")

    pathways = evidence.get("pathways", [])
    if pathways:
        pathway_lines = "\n".join(
            f"  - {p['name']} ({p['url']})" for p in pathways[:10]
        )
        pathway_section = f"PATHWAY CONTEXT:\n{pathway_lines}"
    else:
        pathway_section = "PATHWAY CONTEXT: (no KEGG pathways found)"

    gene_role = evidence.get("gene_role")
    gene_role_line = f"\nGENE ROLE: {gene} is a {gene_role}." if gene_role else ""

    # Precise label + exact percentile per source, so the LLM can cite
    # "93rd percentile" rather than only a coarse High/Medium/Low bucket —
    # two cell lines both labeled "High" can still differ meaningfully.
    def _ev_line(key: str) -> str:
        ev = evidence.get(key) or {}
        label = ev.get("label", "N/A")
        pct   = ev.get("percentile") or "N/A"
        return f"{label} ({pct})"

    precise_section = (
        f"PRECISE EVIDENCE (label + exact percentile per source):\n"
        f"- HPA: {_ev_line('hpa_evidence')}\n"
        f"- DepMap: {_ev_line('depmap_evidence')}\n"
        f"- GEO: {_ev_line('geo_evidence')}\n"
        f"- Proteomics: {_ev_line('protein_evidence')}"
    )

    return f"""CELL LINE: {meta['official_name']} ({evidence['cellosaurus_id']})
GENE QUERIED: {gene}{gene_role_line}

EXPRESSION EVIDENCE:
- HPA RNA (nTPM):       {hpa_line}
- DepMap TPM:           {dep_line}
- GEO ({geo_line}):
  GEO confirmation: {geo_conf_str}
- Proteomics:           {prot_line}

{precise_section}

{crispr_section}

{mutation_section}

CELL LINE PROFILE:
- Disease:              {meta.get('disease', 'unknown')}
- Lineage:              {meta.get('lineage', 'unknown')}
- Nomenclature sources: {meta.get('evidence_count', '?')}/3
- Mutation data:        {'yes' if meta.get('has_mutations') else 'no'}
- Fusion data:          {'yes' if meta.get('has_fusions') else 'no'}
- MSI score:            {meta['msi_score'] if meta.get('msi_score') is not None else 'N/A'}
- Ploidy:               {meta['ploidy'] if meta.get('ploidy') is not None else 'N/A'}

SCORES:
- RNA expression score: {scores['rna_score']:.2f}  (HPA={scores['hpa_score']:.2f}, DepMap={scores['depmap_score']:.2f})
- Protein score:        {scores['protein_score']:.2f}
- Data quality score:   {scores['quality_score']:.2f}
- Context score:        {scores['context_score']:.2f}
- Mutation impact score: {scores.get('mutation_impact_score', 0.0):.2f}
- GEO confirmation:     {scores['geo_confirmation']:+.2f}
- Final fit score:      {scores['final_score']:.2f}

{lit_formatted}

{pathway_section}

CULTURE/ASSAY CONTEXT:
{format_growth_properties(evidence.get("growth_properties"))}
Consider doubling time when assessing suitability for time-sensitive assays (e.g. high-throughput screening favours faster-doubling lines).

Use these papers to support your justification where relevant. Cite as [1], [2] etc."""
