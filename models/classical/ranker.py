from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config import CELL_LINE_LOOKUP
from models.classical.scorer import (
    FIXED_WEIGHTS,
    load_mappings,
    score_context,
    score_data_quality,
    score_protein_expression,
    score_rna_expression,
)

# Re-export for external consumers (evaluate, weights_learned, etc.)
__all__ = ["FIXED_WEIGHTS", "rank", "explain"]


def rank(
    gene: str,
    disease_filter: str | None = None,
    lineage_filter: str | None = None,
    top_n: int | None = 10,
    weights: dict = FIXED_WEIGHTS,
    expression_threshold: bool = True,
    exclude_genes: list[str] | None = None,
) -> pd.DataFrame:
    """
    Rank cell lines by suitability for studying a given gene.

    Final score formula:
        weights["rna"]     * rna_score
      + weights["protein"] * protein_score
      + weights["quality"] * quality_score
      + weights["context"] * context_score
      + geo_confirmation_bonus  (additive ±0.10, not weighted)

    exclude_genes: optional list of gene symbols whose expression should
        penalise the final score. For each excluded gene, an expression score
        is computed and applied as:
            final_score *= (1 - excluded_rna_score * 0.5)
        Columns added: excluded_{g}_score, excluded_{g}_flag (score > 0.5),
        exclusion_warning (True if any flag is set).

    Returns columns:
        cellosaurus_id, official_name, final_score,
        rna_score, protein_score, quality_score, context_score,
        geo_confirmation, n_sources, disease, lineage,
        hpa_score, depmap_score, missing_data_flag,
        exclusion_warning [, excluded_{g}_score, excluded_{g}_flag ...]
    """
    hpa_to_cvcl, ach_to_cvcl, gsm_to_cvcl = load_mappings()

    rna_df     = score_rna_expression(gene, hpa_to_cvcl, gsm_to_cvcl)
    protein_df = score_protein_expression(gene, ach_to_cvcl)

    all_cvcl = set(rna_df["cellosaurus_id"]) | set(protein_df["cellosaurus_id"])
    if not all_cvcl:
        print(f"No expression data found for gene: {gene}")
        return pd.DataFrame()

    result = (
        pd.DataFrame({"cellosaurus_id": list(all_cvcl)})
        .merge(rna_df, on="cellosaurus_id", how="left")
        .merge(protein_df, on="cellosaurus_id", how="left")
    )

    result["rna_score"]       = result["rna_score"].fillna(0.0)
    result["protein_score"]   = result["protein_score"].fillna(0.0)
    result["geo_confirmation"] = result["geo_confirmation"].fillna(0.0)

    quality_df = score_data_quality(all_cvcl, rna_df, protein_df)
    result = result.merge(quality_df, on="cellosaurus_id", how="left")
    result["quality_score"] = result["quality_score"].fillna(0.0)

    context_df = score_context(all_cvcl, disease_filter, lineage_filter)
    result = result.merge(context_df, on="cellosaurus_id", how="left")
    result["context_score"] = result["context_score"].fillna(0.0)

    result["final_score"] = (
        weights["rna"]     * result["rna_score"]
        + weights["protein"] * result["protein_score"]
        + weights["quality"] * result["quality_score"]
        + weights["context"] * result["context_score"]
        + result["geo_confirmation"]   # additive, not weighted
    )
    # Clip to [0,1] - GEO confirmation bonus (+0.10)
    # can push scores above 1.0 for top-ranked lines
    result["final_score"] = result["final_score"].clip(0.0, 1.0)

    # ── Exclusion gene penalties ──────────────────────────────────────────────
    # For each excluded gene, score its RNA expression across all cell lines
    # and apply a multiplicative penalty proportional to that expression.
    # Penalty formula: final_score *= (1 - excl_rna_score * 0.5)
    # A cell line expressing the excluded gene at 0.8 → −40% final score.
    if exclude_genes:
        for excl_gene in exclude_genes:
            excl_rna = score_rna_expression(excl_gene, hpa_to_cvcl, gsm_to_cvcl)
            excl_col = f"excluded_{excl_gene}_score"
            if len(excl_rna) > 0:
                excl_sub = (
                    excl_rna[["cellosaurus_id", "rna_score"]]
                    .rename(columns={"rna_score": excl_col})
                )
                result = result.merge(excl_sub, on="cellosaurus_id", how="left")
            if excl_col not in result.columns:
                result[excl_col] = 0.0
            else:
                result[excl_col] = result[excl_col].fillna(0.0)

            result[f"excluded_{excl_gene}_flag"] = result[excl_col] > 0.5
            penalty = result[excl_col] * 0.5
            result["final_score"] = (result["final_score"] * (1.0 - penalty)).clip(0.0, 1.0)

        flag_cols = [f"excluded_{g}_flag" for g in exclude_genes]
        result["exclusion_warning"] = result[flag_cols].any(axis=1)
    else:
        result["exclusion_warning"] = False

    if disease_filter or lineage_filter:
        result = result[result["context_score"] > 0]

    lkp = pd.read_parquet(CELL_LINE_LOOKUP, columns=["cellosaurus_id", "official_name"])
    result = result.merge(lkp, on="cellosaurus_id", how="left")

    result = result.sort_values("final_score", ascending=False)
    if top_n is not None:
        result = result.head(top_n)

    out_cols = [
        "cellosaurus_id", "official_name", "final_score",
        "rna_score", "protein_score", "quality_score", "context_score",
        "geo_confirmation", "n_sources", "disease", "lineage",
        "hpa_score", "depmap_score", "missing_data_flag",
        "exclusion_warning",
    ]
    if exclude_genes:
        for g in exclude_genes:
            out_cols.extend([f"excluded_{g}_score", f"excluded_{g}_flag"])
    return result[out_cols].reset_index(drop=True)


def explain(row) -> str:
    """Generate a plain-English explanation for one ranked result row."""
    name = (
        row.get("official_name")
        if pd.notna(row.get("official_name"))
        else row.get("cellosaurus_id", "Unknown")
    )

    rna   = float(row.get("rna_score") or 0)
    n     = int(row.get("n_sources") or 0)
    geo_c = float(row.get("geo_confirmation") or 0)

    if rna > 0.8:
        expr_desc = "strongly"
    elif rna > 0.5:
        expr_desc = "moderately"
    elif rna > 0:
        expr_desc = "weakly"
    else:
        expr_desc = "not detectably (no primary RNA data)"

    # Cross-source consistency from available hpa/depmap scores
    hpa_s  = row.get("hpa_score")
    dep_s  = row.get("depmap_score")
    avail  = [float(v) for v in [hpa_s, dep_s] if pd.notna(v)]
    consistency = "high" if len(avail) < 2 else (
        "high" if abs(avail[0] - avail[1]) < 0.15 else
        "moderate" if abs(avail[0] - avail[1]) < 0.35 else "low"
    )

    geo_str = ""
    if geo_c > 0:
        geo_str = " GEO independently confirms expression."
    elif geo_c < 0:
        geo_str = " Note: GEO data contradicts primary RNA sources."

    disease = row.get("disease") or ""
    lineage = row.get("lineage") or ""
    context = float(row.get("context_score") or 0)
    context_str = ""
    if context >= 1.0:
        label = disease if pd.notna(disease) and disease else lineage
        context_str = f" {label} exactly matches query."
    elif context >= 0.5:
        label = disease if pd.notna(disease) and disease else lineage
        context_str = f" {label} partially matches query."

    confidence_pct = int(round(float(row.get("final_score") or 0) * 100))

    return (
        f"{name} expresses the target gene {expr_desc} (RNA score {rna:.2f}) "
        f"confirmed across {n} of 2 primary RNA sources with {consistency} "
        f"consistency.{geo_str}{context_str} Overall confidence: {confidence_pct}%"
    )
