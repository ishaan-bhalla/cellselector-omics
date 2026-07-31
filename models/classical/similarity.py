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

# ── Per-feature weights ────────────────────────────────────────────────────────
# Applied as a multiplicative scale to each column before cosine similarity.
# Expression scores dominate; binary coverage flags are down-weighted so that
# sharing a full data-coverage profile doesn't overshadow expression similarity.

FEATURE_WEIGHTS: dict[str, float] = {
    # Data coverage (binary) — low weight
    "has_metabolomics": 0.3,
    "has_mirna":        0.3,
    "has_proteomics":   0.5,
    "has_hpa_expr":     0.5,
    "has_depmap_expr":  0.5,
    "has_geo_expr":     0.5,
    "has_mutations":    0.3,
    "has_fusions":      0.3,
    # Genomic (normalised continuous) — medium weight
    "MSIScore_norm":    1.0,
    "Ploidy_norm":      1.0,
    "CIN_norm":         1.0,
    "evidence_norm":    1.0,
    # Gene expression profile — high weight
    "hpa_score":        2.5,
    "depmap_score":     2.5,
    "geo_score":        2.0,
    "protein_score":    2.0,
    "rna_score":        3.0,
    "quality_score":    2.0,
    "context_score":    2.0,
}

# Pre-built weight array aligned with FEATURE_NAMES order
_WEIGHT_VECTOR = np.array(
    [FEATURE_WEIGHTS[f] for f in FEATURE_NAMES], dtype=np.float64
)

# Expression features prioritised first when explaining similarity
_EXPRESSION_FEATURES = frozenset(
    ["rna_score", "hpa_score", "depmap_score", "protein_score",
     "geo_score", "quality_score"]
)

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
    # Apply feature weights so expression scores dominate cosine similarity
    matrix          = df[FEATURE_NAMES].values.astype(np.float64) * _WEIGHT_VECTOR
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

    Expression features are checked first; non-expression features fill
    remaining slots. Within each group, features are ranked by informative
    alignment score (high shared value + small difference).
    """
    diffs      = np.abs(query_vec - similar_vec)
    avg_vals   = (query_vec + similar_vec) / 2.0
    info_score = avg_vals / (diffs + 0.05)

    # Split indices: expression features first, everything else after
    expr_idxs  = [i for i, f in enumerate(feature_names) if f in _EXPRESSION_FEATURES]
    other_idxs = [i for i, f in enumerate(feature_names) if f not in _EXPRESSION_FEATURES]

    ordered_idxs = (
        sorted(expr_idxs,  key=lambda i: -float(info_score[i])) +
        sorted(other_idxs, key=lambda i: -float(info_score[i]))
    )

    reasons: list[str] = []
    for idx in ordered_idxs:
        if len(reasons) >= 3:
            break
        feat  = feature_names[idx]
        avg   = float(avg_vals[idx])
        diff  = float(diffs[idx])
        label = _FEATURE_LABELS.get(feat, feat)

        # Skip shared-absence — only informative when both have non-trivial values
        if avg < 0.05 and diff < 0.05:
            continue

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
    disease_filter: str | None = None,
    lineage_filter: str | None = None,
) -> dict[str, list[dict]]:
    """
    Find the most similar alternative cell lines for each recommended line.

    If disease_filter or lineage_filter is supplied, candidates are first
    restricted to cell lines whose disease contains disease_filter OR whose
    lineage contains lineage_filter (case-insensitive substring match).
    If fewer than top_k same-context alternatives exist, the result falls
    back to the unfiltered similarity list and each entry carries a "note"
    field explaining the fallback.

    For accuracy, expression scores are computed for ALL cell lines (via a
    full rank() call with top_n=None), not just the top_n in rank_results_df.

    Returns:
        {cellosaurus_id: [
            {
                "cellosaurus_id":    "CVCL_XXXX",
                "official_name":     "NCI-H1975",
                "similarity_score":  0.94,
                "shared_data_types": ["HPA", "DepMap", "Mutations"],
                "similarity_reason": "both show high HPA expression level; ...",
                "note":              None | "insufficient same-disease ...",
                "citations":         {...}
            },
            ...
        ]}
    """
    # Lazy import avoids circular dependency (similarity ↔ ranker)
    from models.classical.ranker import rank as _rank_full
    from config import CELL_LINE_LOOKUP, DATASET_CITATIONS

    use_context_filter = bool(disease_filter or lineage_filter)

    # ── Expression scores for ALL cell lines ──────────────────────────────────
    print(f"  [similarity] Computing full expression scores for {gene}...")
    full_scores = _rank_full(gene, top_n=None)

    # ── Genomic features ──────────────────────────────────────────────────────
    master_df = pd.read_parquet(master_merged_path)

    # ── Disease / lineage lookup (lives in cell_line_lookup, not master_merged)
    lkp = pd.read_parquet(
        CELL_LINE_LOOKUP, columns=["cellosaurus_id", "disease", "lineage"]
    )
    disease_map  = dict(zip(lkp["cellosaurus_id"], lkp["disease"].fillna("")))
    lineage_map  = dict(zip(lkp["cellosaurus_id"], lkp["lineage"].fillna("")))

    # Pre-build context-match set for fast lookup
    if use_context_filter:
        df_lower = (disease_filter or "").lower()
        lf_lower = (lineage_filter or "").lower()

        def _matches_context(cvcl: str) -> bool:
            d = disease_map.get(cvcl, "").lower()
            l = lineage_map.get(cvcl, "").lower()
            return (df_lower and df_lower in d) or (lf_lower and lf_lower in l)

        context_cvcl_set = {c for c in lkp["cellosaurus_id"] if _matches_context(c)}
    else:
        context_cvcl_set = None

    # ── Build feature matrix and compute similarity ───────────────────────────
    matrix, cvcl_ids = build_feature_matrix(gene, full_scores, master_df)
    name_map = dict(zip(master_df["cellosaurus_id"], master_df["official_name"]))

    query_ids  = rank_results_df["cellosaurus_id"].tolist()
    id_to_idx  = {c: i for i, c in enumerate(cvcl_ids)}

    # Fetch a larger candidate pool so we have enough after context filtering
    fetch_k    = max(top_k * 10, 30) if use_context_filter else top_k
    raw_result = compute_similarity(query_ids, matrix, cvcl_ids, top_k=fetch_k)

    # ── Build citation template (shared across all alternatives) ─────────────
    _citation_template = {
        "data_sources": [
            (
                "Expression similarity computed using "
                "HPA [D1], DepMap [D2], GEO [D3], CCLE Proteomics [D4]"
            ),
            "Cell line identity verified via Cellosaurus [D5]",
        ],
        "method": (
            "Cosine similarity on 19-dimensional normalised "
            "multi-omics feature vector (expression features "
            "weighted 2-3×; coverage flags 0.3-0.5×)"
        ),
        "dataset_keys": {
            k: {
                "name":     v["name"],
                "citation": v["citation"],
                "pmid":     v["pmid"],
                "url":      v["url"],
            }
            for k, v in DATASET_CITATIONS.items()
        },
    }

    def _annotate(s: dict, q_vec: np.ndarray, note: str | None) -> dict:
        """Convert a raw compute_similarity entry into a fully annotated dict."""
        scvcl = s["cellosaurus_id"]
        s_vec = s["_similar_vec"]

        shared = [
            label
            for feat, label in _DATA_TYPE_MAP.items()
            if feat in FEATURE_NAMES
            and float(q_vec[FEATURE_NAMES.index(feat)]) / FEATURE_WEIGHTS.get(feat, 1.0) > 0.5
            and float(s_vec[FEATURE_NAMES.index(feat)]) / FEATURE_WEIGHTS.get(feat, 1.0) > 0.5
        ]

        return {
            "cellosaurus_id":    scvcl,
            "official_name":     name_map.get(scvcl, scvcl),
            "similarity_score":  s["similarity_score"],
            "shared_data_types": shared,
            "similarity_reason": similarity_reason(q_vec, s_vec, FEATURE_NAMES),
            "note":              note,
            "citations": {
                **_citation_template,
                "cellosaurus_url": f"https://www.cellosaurus.org/{scvcl}",
            },
        }

    # ── Annotate and apply context filter per query line ─────────────────────
    result: dict[str, list[dict]] = {}

    for qcvcl, similar_list in raw_result.items():
        if qcvcl not in id_to_idx:
            result[qcvcl] = []
            continue

        q_vec = matrix[id_to_idx[qcvcl]]

        if use_context_filter:
            in_context  = [s for s in similar_list if s["cellosaurus_id"] in context_cvcl_set]
            out_context = [s for s in similar_list if s["cellosaurus_id"] not in context_cvcl_set]

            if len(in_context) >= top_k:
                # Enough same-context alternatives — use them, no fallback note
                chosen = [_annotate(s, q_vec, None) for s in in_context[:top_k]]
            else:
                # Partial match: take what's available in-context, fill with cross-disease
                fallback_note = (
                    "insufficient same-disease alternatives, "
                    "showing cross-disease similar lines"
                )
                chosen = [_annotate(s, q_vec, None) for s in in_context]
                needed = top_k - len(chosen)
                chosen += [_annotate(s, q_vec, fallback_note) for s in out_context[:needed]]
        else:
            chosen = [_annotate(s, q_vec, None) for s in similar_list[:top_k]]

        result[qcvcl] = chosen

    return result
