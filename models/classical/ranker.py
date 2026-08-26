from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config import CELL_LINE_LOOKUP
from models.classical.scorer import (
    FIXED_WEIGHTS,
    _level_label_with_percentile,
    classify_gene,
    load_mappings,
    score_context,
    score_crispr_dependency,
    score_data_quality,
    score_protein_expression,
    score_rna_expression,
)

# Re-export for external consumers (evaluate, weights_learned, etc.)
__all__ = ["FIXED_WEIGHTS", "rank", "explain"]

_CACHED_LEARNED_WEIGHTS: dict | None = None


def _get_learned_weights() -> dict:
    global _CACHED_LEARNED_WEIGHTS
    if _CACHED_LEARNED_WEIGHTS is None:
        from models.classical.weights_learned import optimise_weights
        print("[ranker] Computing learned weights (one-time, cached)...")
        _CACHED_LEARNED_WEIGHTS = optimise_weights()
    return _CACHED_LEARNED_WEIGHTS


def rank(
    gene: str,
    disease_filter: str | None = None,
    lineage_filter: str | None = None,
    top_n: int | None = 10,
    weights: dict | None = None,
    use_learned_weights: bool = True,
    expression_threshold: bool = True,
    exclude_genes: list[str] | None = None,
    include_alternatives: bool = False,
    alternatives_top_k: int = 3,
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

    dependency_score / dependency_percentile: CRISPR gene-essentiality signal
        (DepMap). Answers a different question from expression — how much a
        cell line NEEDS the gene to survive, not how much it makes of it —
        so it is attached as an informational column only and never enters
        the weighted final_score.

    hpa_evidence / depmap_evidence / protein_evidence: dicts of
        {label, score, percentile} — a qualitative Low/Medium/High/No data
        label alongside the exact underlying value, so the label never has
        to stand alone (see scorer._level_label_with_percentile).
        geo_evidence: {label: Confirms/Contradicts/No data, score, percentile
        (always None — GEO's signal is a confirmation bonus, not a rank)}.
        Surfaces per-source agreement or disagreement directly, rather than
        only the blended quality_score.

    vs_next_rank: a concrete, numeric explanation of why this cell line
        ranks above the next one down (see explain_rank_difference), or
        None for the last row.

    Returns columns:
        cellosaurus_id, official_name, final_score,
        rna_score, protein_score, quality_score, context_score,
        geo_confirmation, n_sources, disease, lineage,
        hpa_score, depmap_score, missing_data_flag,
        dependency_score, dependency_percentile,
        hpa_evidence, depmap_evidence, geo_evidence, protein_evidence,
        vs_next_rank,
        exclusion_warning [, excluded_{g}_score, excluded_{g}_flag ...]
    """
    if weights is None:
        weights = _get_learned_weights() if use_learned_weights else FIXED_WEIGHTS

    hpa_to_cvcl, ach_to_cvcl, gsm_to_cvcl = load_mappings()
    gene_class = classify_gene(gene)

    rna_df     = score_rna_expression(gene, hpa_to_cvcl, gsm_to_cvcl,
                                      gene_class=gene_class)
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

    # ── Per-source evidence (label + exact score + percentile) — computed
    # before the fillna(0.0) calls below, which would otherwise collapse
    # "no proteomics data" and "proteomics data present but low" into the
    # same 0.0 and mislabel both as "Low" instead of "No data".
    #
    # hpa_score / depmap_score / protein_score are ALREADY 0-1 percentile
    # ranks (see scorer._pct_rank) computed globally across every cell line
    # with data for this gene — not raw magnitudes. So the "percentile"
    # passed in is the score itself, not a re-rank of it. Re-ranking again
    # here (e.g. via .rank(pct=True) on `result`) would silently produce a
    # LOCAL percentile relative to whatever subset happens to be in
    # `result` at that point (and after top_n truncation, relative to just
    # the displayed top N) — a different, misleading number masquerading
    # as the real one.
    result["hpa_evidence"] = result["hpa_score"].apply(
        lambda s: _level_label_with_percentile(s, s)
    )
    result["depmap_evidence"] = result["depmap_score"].apply(
        lambda s: _level_label_with_percentile(s, s)
    )
    result["protein_evidence"] = result["protein_score"].apply(
        lambda s: _level_label_with_percentile(s, s)
    )
    result["geo_evidence"] = result["geo_confirmation"].apply(
        lambda x: {
            "label": ("Confirms" if x > 0 else "Contradicts" if x < 0 else "No data"),
            "score": round(float(x), 3) if pd.notna(x) else None,
            "percentile": None,
        }
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
    result["final_score"] = result["final_score"].clip(0.0, 1.0)
    result["gene_class"] = classify_gene(gene)

    # ── Exclusion-gene penalties ──────────────────────────────────────────────
    if exclude_genes:
        for excl_gene in exclude_genes:
            excl_rna = score_rna_expression(excl_gene, hpa_to_cvcl, gsm_to_cvcl)
            cvcl_map = dict(zip(excl_rna["cellosaurus_id"], excl_rna["rna_score"]))
            score_col = f"excluded_{excl_gene}_score"
            flag_col  = f"excluded_{excl_gene}_flag"
            result[score_col] = result["cellosaurus_id"].map(
                lambda c, m=cvcl_map: float(m.get(c, 0.0))
            )
            result["final_score"] = (
                result["final_score"] * (1 - result[score_col] * 0.5)
            ).clip(0.0, 1.0)
            result[flag_col] = result[score_col] > 0.5
        result["exclusion_warning"] = result[
            [f"excluded_{g}_flag" for g in exclude_genes]
        ].any(axis=1)

    if disease_filter or lineage_filter:
        result = result[result["context_score"] > 0]

    lkp = pd.read_parquet(CELL_LINE_LOOKUP, columns=["cellosaurus_id", "official_name"])
    result = result.merge(lkp, on="cellosaurus_id", how="left")

    result = result.sort_values("final_score", ascending=False)
    if top_n is not None:
        result = result.head(top_n)

    result["gene_class"] = gene_class

    # ── CRISPR dependency (essentiality) — additive column, NOT weighted ────
    # Kept separate from final_score: essentiality and expression answer
    # different questions, so they must not be blended into one number.
    crispr_df = score_crispr_dependency(gene)
    result = result.merge(crispr_df, on="cellosaurus_id", how="left")

    # ── Adjacent-rank comparisons — must run after final ordering/truncation
    # (sort_values + head(top_n) above) is locked in, since it compares each
    # row to the NEXT row in the returned order.
    result = add_rank_comparisons(result, weights)

    out_cols = [
        "cellosaurus_id", "official_name", "final_score",
        "rna_score", "protein_score", "quality_score", "context_score",
        "geo_confirmation", "n_sources", "disease", "lineage",
        "hpa_score", "depmap_score", "missing_data_flag", "gene_class",
        "dependency_score", "dependency_percentile",
        "hpa_evidence", "depmap_evidence", "geo_evidence", "protein_evidence",
        "vs_next_rank",
    ]
    if exclude_genes:
        out_cols.append("exclusion_warning")
        for g in exclude_genes:
            out_cols.extend([f"excluded_{g}_score", f"excluded_{g}_flag"])

    result = result[out_cols].reset_index(drop=True)

    if include_alternatives:
        # Lazy import avoids circular dependency (ranker ↔ similarity)
        from models.classical.similarity import find_alternatives
        from config import MASTER_MERGED
        alts = find_alternatives(
            gene, result, MASTER_MERGED,
            top_k=alternatives_top_k,
            disease_filter=disease_filter,
            lineage_filter=lineage_filter,
        )
        result["alternatives"] = result["cellosaurus_id"].map(
            lambda cvcl: alts.get(cvcl, [])
        )

    return result


def explain_rank_difference(row_a: pd.Series, row_b: pd.Series, weights: dict) -> str:
    """
    Given two ranked cell lines, explain in concrete numeric terms why
    row_a ranks above/below row_b: which weighted score component
    contributed the most to the gap, and by how much.
    """
    components = ["rna", "protein", "quality", "context"]
    diffs = []
    for comp in components:
        col = f"{comp}_score"
        val_a = row_a.get(col, 0) or 0
        val_b = row_b.get(col, 0) or 0
        weighted_diff = weights[comp] * (val_a - val_b)
        diffs.append((comp, val_a, val_b, weighted_diff))

    diffs.sort(key=lambda x: abs(x[3]), reverse=True)
    top_comp, val_a, val_b, weighted_diff = diffs[0]

    direction = "higher" if weighted_diff > 0 else "lower"
    name_a = row_a.get("official_name", "Cell line A")
    name_b = row_b.get("official_name", "Cell line B")

    return (
        f"{name_a} ranks {'above' if weighted_diff > 0 else 'below'} "
        f"{name_b} primarily due to {direction} {top_comp} "
        f"score ({val_a:.2f} vs {val_b:.2f}, contributing "
        f"{abs(weighted_diff):.3f} to the final score gap)."
    )


def add_rank_comparisons(result: pd.DataFrame, weights: dict) -> pd.DataFrame:
    """
    For each cell line, add an explanation of why it ranks above the
    next-ranked cell line (None for the last row). Must be called after
    `result` is in its final sorted/truncated order — it compares each row
    to the literal next row, not by any score field.
    """
    result = result.reset_index(drop=True)
    comparisons = []
    for i in range(len(result)):
        if i < len(result) - 1:
            comparisons.append(
                explain_rank_difference(result.iloc[i], result.iloc[i + 1], weights)
            )
        else:
            comparisons.append(None)
    result["vs_next_rank"] = comparisons
    return result


def explain(row) -> str:
    """Generate a plain-English explanation for one ranked result row."""
    name = (
        row.get("official_name")
        if pd.notna(row.get("official_name"))
        else row.get("cellosaurus_id", "Unknown")
    )

    gene       = row.get("gene") or ""
    gene_class = row.get("gene_class") or "tissue_specific"
    rna        = float(row.get("rna_score") or 0)
    n          = int(row.get("n_sources") or 0)
    geo_c      = float(row.get("geo_confirmation") or 0)

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

    if gene_class == "ubiquitous":
        # RNA score represents cross-source consistency, not expression level
        if rna > 0.85:
            cons_desc = "very high"
        elif rna > 0.65:
            cons_desc = "good"
        elif rna > 0.4:
            cons_desc = "moderate"
        else:
            cons_desc = "low"
        core = (
            f"{name} shows {cons_desc} cross-source consistency for this "
            f"broadly-expressed gene (consistency score {rna:.2f} across "
            f"{n} of 2 primary RNA sources)."
        )
    else:
        # tissue_specific and loss_of_function: expression-level description
        if rna > 0.8:
            expr_desc = "strongly"
        elif rna > 0.5:
            expr_desc = "moderately"
        elif rna > 0:
            expr_desc = "weakly"
        else:
            expr_desc = "not detectably (no primary RNA data)"

        hpa_s = row.get("hpa_score")
        dep_s = row.get("depmap_score")
        avail = [float(v) for v in [hpa_s, dep_s] if pd.notna(v)]
        consistency = "high" if len(avail) < 2 else (
            "high" if abs(avail[0] - avail[1]) < 0.15 else
            "moderate" if abs(avail[0] - avail[1]) < 0.35 else "low"
        )
        core = (
            f"{name} expresses the target gene {expr_desc} (RNA score {rna:.2f}) "
            f"confirmed across {n} of 2 primary RNA sources with {consistency} consistency."
        )

    lof_note = ""
    if gene_class == "loss_of_function":
        gene_label = gene if gene else "this gene"
        lof_note = (
            f" Note: {gene_label} is typically studied via loss-of-function. "
            f"These results show lines with HIGH expression (useful as controls). "
            f"Lines with known {gene_label} mutations may be more relevant for LOF studies."
        )

    return f"{core}{geo_str}{context_str}{lof_note} Overall confidence: {confidence_pct}%"
