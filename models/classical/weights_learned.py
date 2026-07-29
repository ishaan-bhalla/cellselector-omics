from pathlib import Path
import sys
import warnings

import numpy as np
import pandas as pd
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config import CELL_LINE_LOOKUP
from models.classical.scorer import (
    load_mappings,
    score_context,
    score_data_quality,
    score_protein_expression,
    score_rna_expression,
)

VALIDATION_SET = {
    "EGFR":  ["A-431", "HCC827", "NCI-H1975"],
    "ERBB2": ["SK-BR-3", "AU565", "BT-474"],
    "MYCN":  ["IMR-32", "Kelly", "SK-N-BE(2)"],
    "MET":   ["EBC-1", "Hs 746T"],
    "KIT":   ["Kasumi-1", "GIST882"],
    "TP53":  ["HCT116", "U-2 OS"],
    "BRCA1": ["HCC1937", "MDA-MB-436"],
}

_W_KEYS = ["expression_rna", "expression_protein", "quality", "context"]


def _build_name_to_cvcl() -> dict:
    """Build comprehensive cell-line-name → cellosaurus_id lookup."""
    lkp = pd.read_parquet(
        CELL_LINE_LOOKUP,
        columns=["cellosaurus_id", "official_name", "hpa_name",
                 "geo_name", "depmap_name", "synonyms"],
    )
    mapping: dict[str, str] = {}
    for _, row in lkp.iterrows():
        cvcl = row["cellosaurus_id"]
        for field in ("official_name", "hpa_name", "geo_name", "depmap_name"):
            v = row.get(field)
            if pd.notna(v) and v:
                mapping[str(v).strip().lower()] = cvcl
        syns = row.get("synonyms")
        if pd.notna(syns) and syns:
            for s in str(syns).split(";"):
                s = s.strip()
                if s:
                    mapping[s.lower()] = cvcl
    return mapping


def _precompute_scores(
    validation_set: dict,
    hpa_to_cvcl: dict,
    ach_to_cvcl: dict,
    gsm_to_cvcl: dict,
) -> dict:
    """Pre-compute all component scores for validation genes (called once)."""
    scores = {}
    for gene in validation_set:
        print(f"  Pre-computing {gene}...")
        rna_df     = score_rna_expression(gene, hpa_to_cvcl, gsm_to_cvcl)
        protein_df = score_protein_expression(gene, ach_to_cvcl)

        all_cvcl = set(rna_df["cellosaurus_id"]) | set(protein_df["cellosaurus_id"])
        if not all_cvcl:
            scores[gene] = None
            continue

        result = (
            pd.DataFrame({"cellosaurus_id": list(all_cvcl)})
            .merge(rna_df, on="cellosaurus_id", how="left")
            .merge(protein_df, on="cellosaurus_id", how="left")
        )
        result["rna_score"]     = result["rna_score"].fillna(0.0)
        result["protein_score"] = result["protein_score"].fillna(0.0)

        quality_df = score_data_quality(all_cvcl, rna_df, protein_df)
        result = result.merge(quality_df, on="cellosaurus_id", how="left")
        result["quality_score"] = result["quality_score"].fillna(0.0)

        # Context without a filter: context_score will be 0 for all rows.
        # The optimizer therefore cannot tune the context weight from MRR alone;
        # it is included for completeness but will trend toward zero.
        context_df = score_context(all_cvcl)
        result = result.merge(context_df, on="cellosaurus_id", how="left")
        result["context_score"] = result["context_score"].fillna(0.0)

        scores[gene] = result.set_index("cellosaurus_id")

    return scores


def mrr_score(
    weights: dict,
    validation_set: dict = VALIDATION_SET,
    precomputed: dict | None = None,
) -> float:
    """Compute Mean Reciprocal Rank across the validation gene set.

    Higher MRR is better (maximum = 1.0).
    """
    if precomputed is None:
        hpa, ach, gsm = load_mappings()
        precomputed = _precompute_scores(validation_set, hpa, ach, gsm)

    name_to_cvcl = _build_name_to_cvcl()

    all_rr: list[float] = []
    for gene, known_names in validation_set.items():
        if precomputed.get(gene) is None:
            continue

        df = precomputed[gene].copy()
        df["final_score"] = (
            weights["expression_rna"]     * df["rna_score"]
            + weights["expression_protein"] * df["protein_score"]
            + weights["quality"]            * df["quality_score"]
            + weights["context"]            * df["context_score"]
        )
        df = df.sort_values("final_score", ascending=False).reset_index()

        known_cvcls = {
            name_to_cvcl.get(n.lower())
            for n in known_names
            if name_to_cvcl.get(n.lower())
        }

        for cvcl in known_cvcls:
            hits = df.index[df["cellosaurus_id"] == cvcl].tolist()
            all_rr.append(1.0 / (hits[0] + 1) if hits else 0.0)

    return float(np.mean(all_rr)) if all_rr else 0.0


def optimise_weights(validation_set: dict = VALIDATION_SET) -> dict:
    """Maximise MRR on the validation set via SLSQP with multiple restarts.

    Pre-computes component scores once; the optimiser inner loop is pure
    arithmetic, so it runs fast despite the large number of cell lines.

    Returns the best weight dict found.
    """
    print("Pre-computing validation scores (once)...")
    hpa, ach, gsm = load_mappings()
    precomputed = _precompute_scores(validation_set, hpa, ach, gsm)

    def objective(w_arr: np.ndarray) -> float:
        w = dict(zip(_W_KEYS, w_arr))
        return -mrr_score(w, validation_set, precomputed)

    constraints = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
    bounds = [(0.0, 1.0)] * 4

    starting_points = [
        [0.48, 0.12, 0.25, 0.15],   # fixed weights
        [0.60, 0.10, 0.20, 0.10],
        [0.40, 0.20, 0.30, 0.10],
        [0.50, 0.05, 0.35, 0.10],
        [0.70, 0.10, 0.15, 0.05],
        [0.40, 0.10, 0.40, 0.10],
    ]

    best_result = None
    for x0 in starting_points:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = minimize(
                objective, x0, method="SLSQP",
                bounds=bounds, constraints=constraints,
                options={"ftol": 1e-7, "maxiter": 300},
            )
        if best_result is None or res.fun < best_result.fun:
            best_result = res

    best_weights = dict(zip(_W_KEYS, best_result.x))
    best_mrr = -best_result.fun
    print(f"\nOptimised weights (MRR={best_mrr:.4f}):")
    for k, v in best_weights.items():
        print(f"  {k}: {v:.4f}")

    return best_weights
