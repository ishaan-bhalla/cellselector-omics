from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config import (
    CELL_LINE_LOOKUP,
    GEO_INFO,
    MASTER_MERGED,
    PARQUET_DIR,
    SAMPLE_INFO,
)


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

    # ── 5. Cell line metadata ────────────────────────────────────────────────
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

    # ── 6. Score breakdown ───────────────────────────────────────────────────
    def _f(key: str) -> float:
        return round(float(top_result_df_row.get(key) or 0), 4)

    scores = {
        "rna_score":        _f("rna_score"),
        "hpa_score":        _f("hpa_score"),
        "depmap_score":     _f("depmap_score"),
        "protein_score":    _f("protein_score"),
        "quality_score":    _f("quality_score"),
        "context_score":    _f("context_score"),
        "geo_confirmation": _f("geo_confirmation"),
        "final_score":      _f("final_score"),
    }

    return {
        "gene":              gene,
        "cellosaurus_id":    cellosaurus_id,
        "hpa_expression":    hpa_evidence,
        "depmap_expression": dep_evidence,
        "geo_expression":    geo_evidence,
        "proteomics":        prot_evidence,
        "metadata":          metadata,
        "scores":            scores,
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

    geo_conf = scores["geo_confirmation"]
    geo_conf_str = (
        "GEO CONFIRMS (+0.10 bonus)"  if geo_conf > 0 else
        "GEO CONTRADICTS (-0.10 penalty)" if geo_conf < 0 else
        "no GEO data (neutral)"
    )

    return f"""CELL LINE: {meta['official_name']} ({evidence['cellosaurus_id']})
GENE QUERIED: {gene}

EXPRESSION EVIDENCE:
- HPA RNA (nTPM):       {hpa_line}
- DepMap TPM:           {dep_line}
- GEO ({geo_line}):
  GEO confirmation: {geo_conf_str}
- Proteomics:           {prot_line}

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
- GEO confirmation:     {scores['geo_confirmation']:+.2f}
- Final fit score:      {scores['final_score']:.2f}"""
