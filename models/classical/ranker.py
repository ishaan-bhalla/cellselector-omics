from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config import CELL_LINE_LOOKUP
from models.classical.scorer import (
    load_mappings,
    score_context,
    score_data_quality,
    score_protein_expression,
    score_rna_expression,
)

FIXED_WEIGHTS = {
    "expression_rna":     0.48,
    "expression_protein": 0.12,
    "quality":            0.25,
    "context":            0.15,
}


def rank(
    gene: str,
    disease_filter: str | None = None,
    lineage_filter: str | None = None,
    top_n: int | None = 10,
    weights: dict = FIXED_WEIGHTS,
    expression_threshold: bool = True,
) -> pd.DataFrame:
    """Rank cell lines by suitability for studying a given gene.

    Returns DataFrame with columns:
    cellosaurus_id, official_name, final_score,
    rna_score, protein_score, quality_score, context_score,
    n_sources, disease, lineage, hpa_score, depmap_score, geo_score
    """
    hpa_to_cvcl, ach_to_cvcl, gsm_to_cvcl = load_mappings()

    rna_df = score_rna_expression(gene, hpa_to_cvcl, gsm_to_cvcl)
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

    result["rna_score"]     = result["rna_score"].fillna(0.0)
    result["protein_score"] = result["protein_score"].fillna(0.0)
    result["expr_score"] = (
        weights["expression_rna"]     * result["rna_score"]
        + weights["expression_protein"] * result["protein_score"]
    )

    quality_df = score_data_quality(all_cvcl, rna_df, protein_df)
    result = result.merge(quality_df, on="cellosaurus_id", how="left")
    result["quality_score"] = result["quality_score"].fillna(0.0)

    context_df = score_context(all_cvcl, disease_filter, lineage_filter)
    result = result.merge(context_df, on="cellosaurus_id", how="left")
    result["context_score"] = result["context_score"].fillna(0.0)

    result["final_score"] = (
        result["expr_score"]
        + weights["quality"]  * result["quality_score"]
        + weights["context"]  * result["context_score"]
    )

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
        "n_sources", "disease", "lineage", "hpa_score", "depmap_score", "geo_score",
    ]
    return result[out_cols].reset_index(drop=True)


def explain(row) -> str:
    """Generate a plain-English explanation for one ranked result row."""
    name = (
        row.get("official_name")
        if pd.notna(row.get("official_name"))
        else row.get("cellosaurus_id", "Unknown")
    )

    rna = float(row.get("rna_score") or 0)
    n   = int(row.get("n_sources") or 0)

    if rna > 0.8:
        expr_desc = "strongly"
    elif rna > 0.5:
        expr_desc = "moderately"
    elif rna > 0:
        expr_desc = "weakly"
    else:
        expr_desc = "not detectably (RNA data absent)"

    scores = [row.get(k) for k in ("hpa_score", "depmap_score", "geo_score")]
    avail = [float(v) for v in scores if pd.notna(v)]
    if len(avail) >= 2:
        std = float(np.std(avail))
        consistency = "high" if std < 0.15 else ("moderate" if std < 0.35 else "low")
    else:
        consistency = "high"

    context = float(row.get("context_score") or 0)
    disease = row.get("disease") or ""
    lineage = row.get("lineage") or ""
    context_str = ""
    if context > 0:
        label = disease if pd.notna(disease) and disease else lineage
        context_str = f" {label} lineage matches query."

    confidence_pct = int(round(float(row.get("final_score") or 0) * 100))

    return (
        f"{name} expresses the target gene {expr_desc} (RNA score {rna:.2f}) "
        f"confirmed across {n} of 3 RNA sources with {consistency} consistency."
        f"{context_str} Overall confidence: {confidence_pct}%"
    )
