import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import numpy as np

from config import OUTPUTS_DIR
from models.classical.scorer import classify_gene, load_mappings
from models.classical.weights_learned import (
    VALIDATION_SET,
    _GRID_SEARCH_PATHWAY_WEIGHTS,
    _build_name_to_cvcl,
    _precompute_scores,
    _run_optimisation,
)

# Per-gene RRs for A/B/C are persisted here so other scripts (e.g.
# compare_ranking_methods.py's significance tests) can reuse them without
# re-running this file's ~25-fold SLSQP optimization loops per config.
RESULTS_PATH = OUTPUTS_DIR / "cross_validated_loo_results.json"

# ─────────────────────────────────────────────────────────────────────────────
# Leave-one-out cross-validation. Every MRR reported so far (full_evaluation.py,
# pathway_grid_search.py, the SLSQP per-class fits) is computed IN-SAMPLE —
# weights fit on all 25 genes, then scored on those same 25 genes. That
# doesn't measure generalization; a weight vector can overfit a small,
# rank-based validation set. This holds out each gene in turn, refits
# weights on the other 24, and scores ONLY the held-out gene — the average
# reciprocal rank across all 25 folds is the cross-validated MRR.
#
# Reuses weights_learned._run_optimisation (11 starting points, including a
# pathway-heavy one) for every fold's optimization, rather than a fresh,
# more weakly-started optimizer. This session already found SLSQP can get
# stuck on the pathway dimension's step-function MRR surface when starting
# points are too sparse — running that risk silently across 75 separate
# optimizations (25 folds x 3 configs) would undermine exactly the rigor
# this script exists to add.
# ─────────────────────────────────────────────────────────────────────────────


def _reciprocal_rank_for_gene(
    gene: str, weights: dict, scores_cache: dict, name_to_cvcl: dict
) -> float:
    if gene not in scores_cache or scores_cache[gene] is None:
        return 0.0
    df = scores_cache[gene].copy()

    df["test_score"] = (
        weights["rna"]     * df["rna_score"]
        + weights["protein"] * df["protein_score"]
        + weights["quality"] * df["quality_score"]
        + weights["context"] * df["context_score"]
        + weights.get("pathway", 0.0) * df.get("pathway_activity_score", 0.0)
        + df["geo_confirmation"]
    ).clip(0.0, 1.0)

    # cellosaurus_id is the DataFrame's index (see _precompute_scores'
    # .set_index), not a column — reset_index puts it back as one.
    df = df.sort_values("test_score", ascending=False).reset_index()

    known = {
        name_to_cvcl[n.lower()] for n in VALIDATION_SET[gene] if n.lower() in name_to_cvcl
    }
    if not known:
        return 0.0

    for i, (_, row) in enumerate(df.iterrows(), 1):
        if row["cellosaurus_id"] in known:
            return 1.0 / i
    return 0.0


def leave_one_out_evaluation():
    print("Precomputing all scores (one-time)...")
    hpa, ach, gsm = load_mappings()
    scores_cache = _precompute_scores(VALIDATION_SET, hpa, ach, gsm)
    name_to_cvcl = _build_name_to_cvcl()

    all_genes = list(VALIDATION_SET.keys())
    gene_classes = {g: classify_gene(g) for g in all_genes}

    # ── Config A: global 4D, no pathway ───────────────────────────────────
    print("\n" + "=" * 60)
    print("CONFIG A: Global weights, no pathway (LOO-CV)")
    print("=" * 60)
    per_gene_a: dict[str, float] = {}
    for hold_out in all_genes:
        train = {g: VALIDATION_SET[g] for g in all_genes if g != hold_out}
        weights = _run_optimisation(train, scores_cache, label=f"A/-{hold_out}", include_pathway=False)
        rr = _reciprocal_rank_for_gene(hold_out, weights, scores_cache, name_to_cvcl)
        per_gene_a[hold_out] = rr
        print(f"  {hold_out:10s}  held-out RR={rr:.3f}")
    cv_mrr_a = float(np.mean(list(per_gene_a.values())))
    print(f"\n  LOO-CV MRR (no pathway): {cv_mrr_a:.4f}")

    # ── Config B: global 5D, with pathway ─────────────────────────────────
    print("\n" + "=" * 60)
    print("CONFIG B: Global weights, WITH pathway (LOO-CV)")
    print("=" * 60)
    per_gene_b: dict[str, float] = {}
    for hold_out in all_genes:
        train = {g: VALIDATION_SET[g] for g in all_genes if g != hold_out}
        weights = _run_optimisation(train, scores_cache, label=f"B/-{hold_out}", include_pathway=True)
        rr = _reciprocal_rank_for_gene(hold_out, weights, scores_cache, name_to_cvcl)
        per_gene_b[hold_out] = rr
        print(f"  {hold_out:10s}  held-out RR={rr:.3f}")
    cv_mrr_b = float(np.mean(list(per_gene_b.values())))
    print(f"\n  LOO-CV MRR (with pathway): {cv_mrr_b:.4f}")

    # ── Config C: per-class 4D baseline + grid-search-verified pathway ───
    print("\n" + "=" * 60)
    print("CONFIG C: Per-class weights + grid pathway (LOO-CV)")
    print("=" * 60)
    per_gene_c: dict[str, float] = {}
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

        pw = _GRID_SEARCH_PATHWAY_WEIGHTS.get(hold_out_class, 0.0)
        # Same construction as weights_learned._apply_grid_search_pathway_weights:
        # rescale the 4D baseline by (1-pw) rather than tacking pathway on
        # top of it — that would push the sum above 1.0 (see that
        # function's docstring for the concrete overshoot example).
        weights = {k: v * (1 - pw) for k, v in baseline_4d.items()}
        weights["pathway"] = pw

        rr = _reciprocal_rank_for_gene(hold_out, weights, scores_cache, name_to_cvcl)
        per_gene_c[hold_out] = rr
        print(f"  {hold_out:10s}  class={hold_out_class:18s}  pw={pw:.2f}  held-out RR={rr:.3f}")
    cv_mrr_c = float(np.mean(list(per_gene_c.values())))
    print(f"\n  LOO-CV MRR (per-class + grid pathway): {cv_mrr_c:.4f}")

    # ── Summary ────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("CROSS-VALIDATED EVALUATION SUMMARY")
    print("=" * 60)
    print(f"  Config A (global, no pathway):         {cv_mrr_a:.4f}")
    print(f"  Config B (global, with pathway):       {cv_mrr_b:.4f}")
    print(f"  Config C (per-class, grid pathway):    {cv_mrr_c:.4f}")
    print()
    print("  For reference only — NOT the same quantity: the earlier")
    print("  IN-SAMPLE (not cross-validated) Config 2 result from")
    print("  full_evaluation.py was 0.1826 (weights fit AND scored on the")
    print("  same 25 genes). It measures fit, not generalization; comparing")
    print("  it to cv_mrr_a is illustrative, not a like-for-like delta.")
    print()

    diff = cv_mrr_c - cv_mrr_a
    verb = "IMPROVES" if diff > 0 else ("DEGRADES" if diff < 0 else "leaves unchanged")
    print(f"  Per-class pathway scoring {verb} cross-validated MRR by {diff:+.4f}")

    results = {
        "cv_mrr":     {"A": cv_mrr_a, "B": cv_mrr_b, "C": cv_mrr_c},
        "per_gene_rr": {"A": per_gene_a, "B": per_gene_b, "C": per_gene_c},
    }
    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved per-gene results → {RESULTS_PATH}")

    return results


if __name__ == "__main__":
    leave_one_out_evaluation()
