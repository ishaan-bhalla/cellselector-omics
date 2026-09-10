import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import numpy as np

from models.classical.scorer import classify_gene, load_mappings
from models.classical.weights_learned import (
    VALIDATION_SET,
    _build_name_to_cvcl,
    _precompute_scores,
    optimise_weights_by_class,
)

# ─────────────────────────────────────────────────────────────────────────────
# Precision@k, split by gene class, as a quick supplementary diagnostic to
# MRR — a hit anywhere in the top-k counts equally whether it's rank 1 or
# rank k, which MRR doesn't show directly.
#
# Weights here are fit ONCE on all 25 genes (in-sample), same methodology
# as Config C (per-class + grid-search pathway) in cross_validated_evaluation.py
# and full_evaluation.py — NOT leave-one-out. That's a deliberate choice for
# a "quick script": refitting per-fold per-k (3 k values x 25 folds) would
# just re-run the ~expensive LOO-CV loop three times over for no benefit,
# since precision@k and RR share the same ranking. Precision@k numbers below
# are therefore in-sample and should not be quoted alongside the LOO-CV MRR
# figures as if they were computed the same way.
# ─────────────────────────────────────────────────────────────────────────────

K_VALUES = [5, 10, 20]


def precision_at_k(df, known_cvcls, k):
    """
    1 if any known correct cell line appears in the top-k by final_score,
    else 0. cellosaurus_id is the DataFrame's index (see
    weights_learned._precompute_scores' .set_index), not a column —
    reset_index puts it back as one before we can read it per-row.
    """
    df_sorted = df.sort_values("final_score", ascending=False).reset_index()
    top_k = df_sorted.head(k)
    return 1 if any(c in known_cvcls for c in top_k["cellosaurus_id"]) else 0


def run_precision_at_k():
    print("Fitting per-class weights (in-sample, all 25 genes)...")
    class_weights = optimise_weights_by_class(VALIDATION_SET, include_pathway=True)
    # loss_of_function has too few dedicated genes to fit its own weights
    # (see optimise_weights_by_class's docstring) — fall back to
    # tissue_specific's weights for scoring those genes, same convention
    # used elsewhere in this codebase.
    if class_weights["loss_of_function"] is None:
        class_weights["loss_of_function"] = class_weights["tissue_specific"]

    hpa, ach, gsm = load_mappings()
    scores_cache = _precompute_scores(VALIDATION_SET, hpa, ach, gsm)
    name_to_cvcl = _build_name_to_cvcl()

    all_genes = list(VALIDATION_SET.keys())
    gene_classes = {g: classify_gene(g) for g in all_genes}

    def known_cvcls_for(gene):
        s = set()
        for name in VALIDATION_SET[gene]:
            cvcl = name_to_cvcl.get(name.lower())
            if cvcl:
                s.add(cvcl)
        return s

    results = {g: {} for g in all_genes}
    for gene in all_genes:
        if gene not in scores_cache or scores_cache[gene] is None:
            for k in K_VALUES:
                results[gene][k] = 0
            continue

        weights = class_weights[gene_classes[gene]]
        df = scores_cache[gene].copy()
        df["final_score"] = (
            weights["rna"]     * df["rna_score"]
            + weights["protein"] * df["protein_score"]
            + weights["quality"] * df["quality_score"]
            + weights["context"] * df["context_score"]
            + weights.get("pathway", 0.0) * df.get("pathway_activity_score", 0.0)
            + df["geo_confirmation"]
        ).clip(0.0, 1.0)

        known = known_cvcls_for(gene)
        for k in K_VALUES:
            results[gene][k] = precision_at_k(df, known, k) if known else 0

    # ── Per-gene table ────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("PRECISION@K BY GENE")
    print("=" * 60)
    header = f"  {'Gene':10s} {'Class':18s} " + "".join(f"P@{k:<6d}" for k in K_VALUES)
    print(header)
    for gene in all_genes:
        row = f"  {gene:10s} {gene_classes[gene]:18s} "
        row += "".join(f"{results[gene][k]:<8d}" for k in K_VALUES)
        print(row)

    # ── Split by class ────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("PRECISION@K BY GENE CLASS (mean over genes in class)")
    print("=" * 60)
    for cls in ["tissue_specific", "ubiquitous", "loss_of_function"]:
        genes_in_cls = [g for g in all_genes if gene_classes[g] == cls]
        if not genes_in_cls:
            continue
        print(f"\n  {cls}  (n={len(genes_in_cls)} genes)")
        for k in K_VALUES:
            vals = [results[g][k] for g in genes_in_cls]
            print(f"    P@{k:<3d}: {np.mean(vals):.3f}  ({sum(vals)}/{len(vals)} genes hit)")

    # ── Overall ───────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("PRECISION@K OVERALL (all 25 genes)")
    print("=" * 60)
    for k in K_VALUES:
        vals = [results[g][k] for g in all_genes]
        print(f"  P@{k:<3d}: {np.mean(vals):.3f}  ({sum(vals)}/{len(vals)} genes hit)")

    return results


if __name__ == "__main__":
    run_precision_at_k()
