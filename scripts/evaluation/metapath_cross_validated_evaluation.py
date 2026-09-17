import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import numpy as np
import pandas as pd

from config import OUTPUTS_DIR
from models.classical.scorer import classify_gene, load_mappings, rank_sort
from models.classical.copy_number_scorer import (
    AMPLIFICATION_COPY_NUMBER_WEIGHT,
    AMPLIFICATION_DRIVEN_GENES,
    apply_amplification_copy_number_weight,
)
from models.classical.rwr_scorer import apply_rwr_weight
from models.classical.metapath_scorer import score_metapath
from models.classical.ranker import WILD_TYPE_MUTATION_PENALTY, WILD_TYPE_PREFERRED_GENES
from models.classical.weights_learned import (
    VALIDATION_SET,
    _GRID_SEARCH_PATHWAY_WEIGHTS,
    _LOF_PRODUCTION_MUTATION_WEIGHT,
    _LOF_PRODUCTION_PATHWAY_WEIGHT,
    _build_name_to_cvcl,
    _precompute_scores,
    _run_optimisation,
)

# ─────────────────────────────────────────────────────────────────────────────
# Held-out (LOO-CV) evaluation of metapath blending, following EXACTLY the
# same Config C construction as cross_validated_evaluation.py (per-class 4D
# baseline, refit per fold on the OTHER genes in that class + RWR at the
# grid-verified class weight) — this file does NOT reimplement or diverge
# from that construction, it reuses the identical pieces
# (weights_learned._run_optimisation, apply_rwr_weight, the
# LOF-mutation/amplification/pathway branch logic) so "Config C" computed
# here is directly comparable to cross_validated_evaluation.py's own.
#
# Config D = Config C + metapath, layered on last (same "applied last, on
# top of whatever branch produced" order RWR itself uses), at the
# STEP-3-grid-search-verified per-class weight — NOT re-optimized per fold.
# This mirrors how RWR's own class weights (RWR_WEIGHT_BY_CLASS) are fixed
# constants from a prior grid search, not something LOO-CV refits per fold;
# refitting metapath's weight per fold would let the held-out gene leak
# information about its own optimal weight into its own evaluation.
#
# Config C and D are computed in the SAME pass over the same 44 folds (same
# baseline_4d fit reused for both), which is what makes the paired
# bootstrap significance test in this task's STEP 4 valid — both configs
# see the exact same train/test splits and the exact same fold-level
# baseline weights, differing ONLY in whether metapath is layered on.
# ─────────────────────────────────────────────────────────────────────────────

METAPATH_WEIGHT_BY_CLASS = {
    # From this task's STEP 3 grid search (44-gene validation set, current
    # production formula incl. RWR + TP53 fix): tissue_specific's peak
    # (+0.0189 in-sample MRR) at w=0.17; ubiquitous showed NO benefit at
    # any weight (best=0.00, i.e. inert here by construction); LOF's small
    # (+0.0042), non-monotonic-shaped peak at w=0.05, included for
    # completeness though flagged as likely noise given n=16.
    "tissue_specific":  0.17,
    "ubiquitous":       0.00,
    "loss_of_function": 0.05,
}

RESULTS_PATH = OUTPUTS_DIR / "metapath_cross_validated_loo_results.json"


def _add_metapath_column(scores_cache: dict) -> None:
    """Mutates scores_cache in place, merging metapath_score onto every
    gene's cached DataFrame — mirrors how rwr_score/copy_number_score are
    merged in weights_learned._precompute_scores, just done here instead
    of touching that shared function for a still-experimental signal."""
    for gene, df in scores_cache.items():
        if df is None:
            continue
        mp_df = score_metapath(gene).set_index("cellosaurus_id")
        df["metapath_score"] = mp_df["metapath_score"].reindex(df.index).fillna(0.0)


def _reciprocal_rank_for_gene(
    gene: str, weights: dict, scores_cache: dict, name_to_cvcl: dict
) -> float:
    """Identical to cross_validated_evaluation.py's own version, plus a
    metapath term (weights.get("metapath", 0.0) defaults to 0.0, so this
    function is a strict superset — passing a Config-C-shaped weights dict
    with no "metapath" key reproduces that script's Config C exactly)."""
    if gene not in scores_cache or scores_cache[gene] is None:
        return 0.0
    df = scores_cache[gene].copy()

    wild_type_penalty = (
        WILD_TYPE_MUTATION_PENALTY * df.get("mutation_impact_score", 0.0)
        if gene in WILD_TYPE_PREFERRED_GENES else 0.0
    )
    df["test_score"] = (
        weights.get("rna", 0.0)     * df["rna_score"]
        + weights.get("protein", 0.0) * df["protein_score"]
        + weights.get("quality", 0.0) * df["quality_score"]
        + weights.get("context", 0.0) * df["context_score"]
        + weights.get("pathway", 0.0) * df.get("pathway_activity_score", 0.0)
        + weights.get("mutation", 0.0) * df.get("mutation_impact_score", 0.0)
        + weights.get("copy_number", 0.0) * df.get("copy_number_score", 0.0)
        + weights.get("rwr", 0.0) * df.get("rwr_score", 0.0)
        + weights.get("metapath", 0.0) * df.get("metapath_score", 0.0)
        + df["geo_confirmation"]
        - wild_type_penalty
    ).clip(0.0, 1.0)

    df = rank_sort(df, "test_score")

    known = {
        name_to_cvcl[n.lower()] for n in VALIDATION_SET[gene] if n.lower() in name_to_cvcl
    }
    if not known:
        return 0.0

    for i, (_, row) in enumerate(df.iterrows(), 1):
        if row["cellosaurus_id"] in known:
            return 1.0 / i
    return 0.0


def _build_config_c_weights(hold_out: str, hold_out_class: str, baseline_4d: dict) -> dict:
    """EXACT replica of cross_validated_evaluation.py's Config C branch
    logic (LOF mutation / amplification copy-number / grid pathway, then
    RWR layered on top) — see that file for the reasoning."""
    if hold_out_class == "loss_of_function":
        mw, pw = _LOF_PRODUCTION_MUTATION_WEIGHT, _LOF_PRODUCTION_PATHWAY_WEIGHT
        weights = {k: v * (1 - mw - pw) for k, v in baseline_4d.items()}
        weights["mutation"] = mw
        if pw > 0:
            weights["pathway"] = pw
    elif hold_out in AMPLIFICATION_DRIVEN_GENES:
        weights = apply_amplification_copy_number_weight(baseline_4d)
    else:
        pw = _GRID_SEARCH_PATHWAY_WEIGHTS.get(hold_out_class, 0.0)
        weights = {k: v * (1 - pw) for k, v in baseline_4d.items()}
        weights["pathway"] = pw

    weights = apply_rwr_weight(weights, hold_out_class)
    return weights


def _apply_metapath_weight(weights: dict, gene_class: str) -> dict:
    """Same rescale-by-(1-w) construction used for every other weight
    decision this project has made (pathway, RWR, copy_number) — shrinks
    the whole Config-C vector proportionally, adds "metapath" so the
    vector still sums to 1.0."""
    mw = METAPATH_WEIGHT_BY_CLASS.get(gene_class, 0.0)
    if mw <= 0:
        return weights
    scale = 1.0 - mw
    out = {k: v * scale for k, v in weights.items()}
    out["metapath"] = mw
    return out


def leave_one_out_evaluation_metapath():
    print("Precomputing all scores (one-time, incl. metapath_score)...")
    hpa, ach, gsm = load_mappings()
    scores_cache = _precompute_scores(VALIDATION_SET, hpa, ach, gsm)
    _add_metapath_column(scores_cache)
    name_to_cvcl = _build_name_to_cvcl()

    all_genes = list(VALIDATION_SET.keys())
    gene_classes = {g: classify_gene(g) for g in all_genes}

    print("\n" + "=" * 60)
    print("CONFIG C (Production+RWR) vs CONFIG D (Production+RWR+Metapath)")
    print("Paired LOO-CV — same fold, same baseline weights, differ only in metapath")
    print("=" * 60)

    per_gene_c: dict[str, float] = {}
    per_gene_d: dict[str, float] = {}

    for hold_out in all_genes:
        hold_out_class = gene_classes[hold_out]
        cls_train = {
            g: VALIDATION_SET[g] for g in all_genes
            if g != hold_out and gene_classes[g] == hold_out_class
        }

        if len(cls_train) >= 2:
            baseline_4d = _run_optimisation(
                cls_train, scores_cache, label=f"C/-{hold_out}", include_pathway=False
            )
        else:
            baseline_4d = {"rna": 0.4, "protein": 0.2, "quality": 0.3, "context": 0.1}

        weights_c = _build_config_c_weights(hold_out, hold_out_class, baseline_4d)
        weights_d = _apply_metapath_weight(dict(weights_c), hold_out_class)

        rr_c = _reciprocal_rank_for_gene(hold_out, weights_c, scores_cache, name_to_cvcl)
        rr_d = _reciprocal_rank_for_gene(hold_out, weights_d, scores_cache, name_to_cvcl)
        per_gene_c[hold_out] = rr_c
        per_gene_d[hold_out] = rr_d
        flag = "" if abs(rr_d - rr_c) < 1e-9 else f"  <-- CHANGED ({rr_d - rr_c:+.3f})"
        print(f"  {hold_out:10s}  class={hold_out_class:18s}  C={rr_c:.3f}  D={rr_d:.3f}{flag}")

    cv_mrr_c = float(np.mean(list(per_gene_c.values())))
    cv_mrr_d = float(np.mean(list(per_gene_d.values())))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Config C (Production+RWR):          LOO-CV MRR = {cv_mrr_c:.4f}")
    print(f"  Config D (Production+RWR+Metapath): LOO-CV MRR = {cv_mrr_d:.4f}")
    print(f"  Delta: {cv_mrr_d - cv_mrr_c:+.4f}")

    for cls in ("tissue_specific", "ubiquitous", "loss_of_function"):
        genes_in_class = [g for g in all_genes if gene_classes[g] == cls]
        c_cls = float(np.mean([per_gene_c[g] for g in genes_in_class]))
        d_cls = float(np.mean([per_gene_d[g] for g in genes_in_class]))
        print(f"  {cls:18s} ({len(genes_in_class):2d} genes): C={c_cls:.4f} -> D={d_cls:.4f}  ({d_cls - c_cls:+.4f})")

    results = {
        "cv_mrr": {"C_production_rwr": cv_mrr_c, "D_production_rwr_metapath": cv_mrr_d},
        "per_gene_rr": {"C": per_gene_c, "D": per_gene_d},
        "gene_classes": gene_classes,
        "metapath_weight_by_class": METAPATH_WEIGHT_BY_CLASS,
    }
    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved per-gene results -> {RESULTS_PATH}")

    return results


if __name__ == "__main__":
    leave_one_out_evaluation_metapath()
