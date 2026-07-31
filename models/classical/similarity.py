from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# ── Feature vector definition ─────────────────────────────────────────────────
# 19-dimensional per-cell-line representation combining:
#   - 8 binary data-coverage flags from master_merged
#   - 4 normalised continuous genomic attributes
#   - 7 gene-specific expression scores

FEATURE_NAMES: list[str] = [
    # Data coverage (binary)
    "has_metabolomics", "has_mirna", "has_proteomics",
    "has_hpa_expr", "has_depmap_expr", "has_geo_expr",
    "has_mutations", "has_fusions",
    # Genomic characteristics (normalised 0-1)
    "MSIScore_norm", "Ploidy_norm", "CIN_norm", "evidence_norm",
    # Gene-specific expression profile (0-1 scores)
    "hpa_score", "depmap_score", "geo_score",
    "protein_score", "rna_score", "quality_score", "context_score",
]

_FEATURE_LABELS: dict[str, str] = {
    "has_metabolomics": "metabolomics data coverage",
    "has_mirna":        "miRNA data coverage",
    "has_proteomics":   "proteomics coverage",
    "has_hpa_expr":     "HPA RNA expression data",
    "has_depmap_expr":  "DepMap RNA expression data",
    "has_geo_expr":     "GEO expression data",
    "has_mutations":    "mutation data",
    "has_fusions":      "fusion gene data",
    "MSIScore_norm":    "microsatellite instability score",
    "Ploidy_norm":      "genomic ploidy",
    "CIN_norm":         "chromosomal instability index",
    "evidence_norm":    "nomenclature source coverage",
    "hpa_score":        "HPA expression level",
    "depmap_score":     "DepMap expression level",
    "geo_score":        "GEO expression signal",
    "protein_score":    "protein expression level",
    "rna_score":        "combined RNA expression",
    "quality_score":    "data quality",
    "context_score":    "tissue/disease relevance",
}

# Binary feature → human-readable data-type label (used for shared_data_types)
_DATA_TYPE_MAP: dict[str, str] = {
    "has_hpa_expr":     "HPA",
    "has_depmap_expr":  "DepMap",
    "has_geo_expr":     "GEO",
    "has_proteomics":   "Proteomics",
    "has_metabolomics": "Metabolomics",
    "has_mirna":        "miRNA",
    "has_mutations":    "Mutations",
    "has_fusions":      "Fusions",
}


# ── Feature matrix construction ────────────────────────────────────────────────

def build_feature_matrix(
    gene: str,
    rank_results_df: pd.DataFrame,
    all_cell_lines_df: pd.DataFrame,
) -> tuple[np.ndarray, list[str]]:
    """
    Build a normalised (n_cells × 19) feature matrix for all cell lines.

    Genomic features come from all_cell_lines_df (master_merged).
    Expression scores come from rank_results_df where available;
    cell lines absent from that DataFrame receive 0 for expression features.

    Returns:
        feature_matrix  — float64 numpy array  (n_cells, len(FEATURE_NAMES))
        cellosaurus_ids — list of CVCL_ IDs matching each row
    """
    df = all_cell_lines_df.copy()

    # ── Binary data-coverage features ─────────────────────────────────────────
    binary_cols = [
        "has_metabolomics", "has_mirna", "has_proteomics",
        "has_hpa_expr", "has_depmap_expr", "has_geo_expr",
        "has_mutations", "has_fusions",
    ]
    for col in binary_cols:
        if col in df.columns:
            df[col] = df[col].fillna(0).astype(float)
        else:
            df[col] = 0.0

    # ── Continuous genomic features (min-max normalised to 0-1) ───────────────
    def _mm(series: pd.Series, fill_val: float) -> pd.Series:
        s  = series.fillna(fill_val)
        lo, hi = float(s.min()), float(s.max())
        if hi > lo:
            return (s - lo) / (hi - lo)
        return pd.Series(0.0, index=s.index)

    if "MSIScore" in df.columns:
        df["MSIScore_norm"] = _mm(df["MSIScore"], fill_val=0.0)
    else:
        df["MSIScore_norm"] = 0.0

    if "Ploidy" in df.columns:
        ploidy_med = float(df["Ploidy"].median())
        df["Ploidy_norm"] = _mm(df["Ploidy"], fill_val=ploidy_med)
    else:
        df["Ploidy_norm"] = 0.0

    if "CIN" in df.columns:
        df["CIN_norm"] = _mm(df["CIN"], fill_val=0.0)
    else:
        df["CIN_norm"] = 0.0

    if "evidence_count" in df.columns:
        df["evidence_norm"] = (df["evidence_count"].fillna(0) / 3.0).clip(0.0, 1.0)
    else:
        df["evidence_norm"] = 0.0

    # ── Gene-specific expression scores from rank_results_df ──────────────────
    expr_src_cols = [
        "cellosaurus_id", "hpa_score", "depmap_score", "geo_confirmation",
        "protein_score", "rna_score", "quality_score", "context_score",
    ]
    if rank_results_df is not None and len(rank_results_df) > 0:
        avail    = [c for c in expr_src_cols if c in rank_results_df.columns]
        expr_sub = rank_results_df[avail].copy()

        # geo_confirmation (±0.10) → geo_score (0-1):
        #   +0.10 → 1.0 (confirmed), 0 → 0.5 (neutral), -0.10 → 0.0 (contradicted)
        if "geo_confirmation" in expr_sub.columns:
            expr_sub["geo_score"] = (
                (expr_sub["geo_confirmation"] / 0.10) + 1.0
            ) / 2.0
            expr_sub["geo_score"] = expr_sub["geo_score"].clip(0.0, 1.0).fillna(0.5)
            expr_sub = expr_sub.drop(columns=["geo_confirmation"])

        df = df.merge(expr_sub, on="cellosaurus_id", how="left")

    # Fill any missing expression columns with 0
    for col in ["hpa_score", "depmap_score", "geo_score",
                "protein_score", "rna_score", "quality_score", "context_score"]:
        if col not in df.columns:
            df[col] = 0.0
        else:
            df[col] = df[col].fillna(0.0)

    df = df.reset_index(drop=True)
    matrix         = df[FEATURE_NAMES].values.astype(np.float64)
    cellosaurus_ids = df["cellosaurus_id"].tolist()

    return matrix, cellosaurus_ids


# ── Cosine similarity ──────────────────────────────────────────────────────────

def compute_similarity(
    query_cellosaurus_ids: list[str],
    feature_matrix: np.ndarray,
    cellosaurus_ids: list[str],
    top_k: int = 5,
) -> dict[str, list[dict]]:
    """
    Compute cosine similarity between each query cell line and all others.

    query_cellosaurus_ids — recommended lines to find alternatives for
    feature_matrix        — (n_cells × n_features) normalised array
    cellosaurus_ids       — CVCL_ IDs matching each matrix row
    top_k                 — how many similar alternatives to return

    Returns:
        {cvcl: [{"cellosaurus_id": ..., "similarity_score": float,
                 "_query_vec": ndarray, "_similar_vec": ndarray}, ...]}

    Internal _query_vec / _similar_vec keys are used by similarity_reason()
    and stripped by find_alternatives() before returning to callers.
    """
    id_to_idx  = {cvcl: i for i, cvcl in enumerate(cellosaurus_ids)}
    query_set  = set(query_cellosaurus_ids)

    # Normalise row-wise for cosine similarity
    norms  = np.linalg.norm(feature_matrix, axis=1, keepdims=True)
    norms  = np.where(norms == 0, 1e-8, norms)
    normed = feature_matrix / norms          # (n_cells, n_features)

    output: dict[str, list[dict]] = {}

    for qcvcl in query_cellosaurus_ids:
        if qcvcl not in id_to_idx:
            output[qcvcl] = []
            continue

        q_idx = id_to_idx[qcvcl]
        sims  = normed @ normed[q_idx]       # cosine sim vs every row

        # Zero-out query lines so they don't appear as their own alternatives
        for excl in query_set:
            if excl in id_to_idx:
                sims[id_to_idx[excl]] = -1.0

        top_idxs = np.argsort(sims)[::-1][:top_k]

        similar = []
        for idx in top_idxs:
            if sims[idx] < 0:
                continue
            similar.append({
                "cellosaurus_id":   cellosaurus_ids[idx],
                "similarity_score": float(round(float(sims[idx]), 4)),
                "_query_vec":       feature_matrix[q_idx],
                "_similar_vec":     feature_matrix[idx],
            })

        output[qcvcl] = similar

    return output


# ── Plain-English reason ───────────────────────────────────────────────────────

def similarity_reason(
    query_vec: np.ndarray,
    similar_vec: np.ndarray,
    feature_names: list[str],
) -> str:
    """
    Generate a plain-English explanation for why two cell lines are similar.

    Identifies up to 3 features where both vectors have meaningfully close
    and non-trivially high values — prioritising informative alignments
    over shared absence.
    """
    diffs     = np.abs(query_vec - similar_vec)
    avg_vals  = (query_vec + similar_vec) / 2.0

    # Score: high average value + small difference = most informative match
    info_score = avg_vals / (diffs + 0.05)
    top_idxs   = np.argsort(info_score)[::-1]

    reasons: list[str] = []
    for idx in top_idxs:
        if len(reasons) >= 3:
            break
        feat  = feature_names[idx]
        avg   = float(avg_vals[idx])
        diff  = float(diffs[idx])
        label = _FEATURE_LABELS.get(feat, feat)

        if avg < 0.05 and diff < 0.05:
            continue   # both near zero — shared absence, not interesting

        if avg >= 0.65 and diff <= 0.20:
            reasons.append(f"both show high {label}")
        elif avg >= 0.35 and diff <= 0.25:
            reasons.append(f"similar {label}")
        elif diff <= 0.15:
            reasons.append(f"comparable {label}")

    return "; ".join(reasons) if reasons else "similar multi-omics profile"


# ── Main entry point ───────────────────────────────────────────────────────────

def find_alternatives(
    gene: str,
    rank_results_df: pd.DataFrame,
    master_merged_path,
    top_k: int = 3,
) -> dict[str, list[dict]]:
    """
    Find the most similar alternative cell lines for each recommended line.

    For accuracy, expression scores are computed for ALL cell lines (via a
    full rank() call), not just the top_n already in rank_results_df.

    Returns:
        {cellosaurus_id: [
            {
                "cellosaurus_id":   "CVCL_XXXX",
                "official_name":    "NCI-H1975",
                "similarity_score": 0.94,
                "shared_data_types": ["HPA", "DepMap", "Mutations"],
                "similarity_reason": "both show high HPA expression level; ..."
            },
            ...
        ]}
    """
    # Lazy import avoids circular dependency (similarity ↔ ranker)
    from models.classical.ranker import rank as _rank_full

    # Score gene across ALL ranked cell lines (top_n=None) for the feature matrix
    print(f"  [similarity] Computing full expression scores for {gene}...")
    full_scores = _rank_full(gene, top_n=None)

    # Load genomic features for all 2,076 cell lines
    master_df = pd.read_parquet(master_merged_path)

    # Build feature matrix
    matrix, cvcl_ids = build_feature_matrix(gene, full_scores, master_df)

    # Name lookup
    name_map = dict(zip(master_df["cellosaurus_id"], master_df["official_name"]))

    # Compute similarity for each recommended line
    query_ids  = rank_results_df["cellosaurus_id"].tolist()
    id_to_idx  = {c: i for i, c in enumerate(cvcl_ids)}
    raw_result = compute_similarity(query_ids, matrix, cvcl_ids, top_k=top_k)

    # Annotate with names, shared data types, and plain-English reasons
    result: dict[str, list[dict]] = {}

    for qcvcl, similar_list in raw_result.items():
        if qcvcl not in id_to_idx:
            result[qcvcl] = []
            continue

        q_vec   = matrix[id_to_idx[qcvcl]]
        cleaned = []

        for s in similar_list:
            scvcl = s["cellosaurus_id"]
            s_vec = s["_similar_vec"]

            shared = [
                label
                for feat, label in _DATA_TYPE_MAP.items()
                if feat in FEATURE_NAMES
                and float(q_vec[FEATURE_NAMES.index(feat)]) > 0.5
                and float(s_vec[FEATURE_NAMES.index(feat)]) > 0.5
            ]

            reason = similarity_reason(q_vec, s_vec, FEATURE_NAMES)

            cleaned.append({
                "cellosaurus_id":    scvcl,
                "official_name":     name_map.get(scvcl, scvcl),
                "similarity_score":  s["similarity_score"],
                "shared_data_types": shared,
                "similarity_reason": reason,
            })

        result[qcvcl] = cleaned

    return result
