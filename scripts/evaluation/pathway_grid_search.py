import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from models.classical.scorer import classify_gene, load_mappings
from models.classical.weights_learned import (
    VALIDATION_SET,
    _build_name_to_cvcl,
    _precompute_scores,
    _run_optimisation,
)

# ─────────────────────────────────────────────────────────────────────────────
# Brute-force grid search over JUST the pathway weight, per gene class,
# holding the other four weights at EACH CLASS'S OWN independently
# 4D-optimized baseline (include_pathway=False) — not the global 4D weights,
# and not the non-pathway components lifted out of a 5D solution (those
# don't sum to 1.0 on their own once pathway's share is removed).
#
# Purpose: SLSQP's per-class 5D result is gradient-based on an objective
# (MRR) that's a step function of rank — flat almost everywhere, so it can
# report back whichever of its starting points scored best rather than a
# genuinely refined optimum (see prior turn's caveat on the exact-starting-
# point matches for tissue_specific/ubiquitous). An exhaustive 1-D sweep has
# no such failure mode and either confirms or overturns that result.
#
# At each candidate pathway weight pw, the WHOLE 5-vector is renormalized to
# sum to 1.0 — base_i * (1-pw) for the four base weights, pw for pathway —
# rather than naively adding pw on top of an already-1.0 base. The naive
# version sums to 1.0+pw, silently clipped by final_score's .clip(0,1): at
# pw=0.50 many cell lines saturate to a tied 1.0, collapsing exactly the
# discriminative signal this search exists to measure, and making the
# result incomparable to SLSQP's simplex-constrained (sum=1.0) 5D solution.
# ─────────────────────────────────────────────────────────────────────────────


def grid_search_pathway_weight():
    print("Precomputing scores (one-time)...")
    hpa, ach, gsm = load_mappings()
    scores_cache = _precompute_scores(VALIDATION_SET, hpa, ach, gsm)
    name_to_cvcl = _build_name_to_cvcl()

    classified: dict[str, list[str]] = {}
    for gene in VALIDATION_SET:
        classified.setdefault(classify_gene(gene), []).append(gene)

    print("\nFitting each class's OWN 4D (no-pathway) baseline — the "
          "'other 4 weights' the grid search holds fixed while pathway varies...")
    base_weights: dict[str, dict] = {}
    for cls, genes in classified.items():
        subset = {g: VALIDATION_SET[g] for g in genes}
        base_weights[cls] = _run_optimisation(
            subset, scores_cache, label=f"{cls} (4D baseline)", include_pathway=False
        )

    print()
    print("=" * 60)
    print("PATHWAY WEIGHT GRID SEARCH BY GENE CLASS")
    print("=" * 60)

    for gene_class, genes in classified.items():
        base = base_weights[gene_class]

        print(f"\n--- {gene_class} ({len(genes)} genes) ---")
        print(f"Base weights (this class's own 4D optimum): {base}")
        print(f"{'pathway_w':>10s} {'MRR':>8s}")
        print("-" * 50)

        best_w = 0.0
        best_mrr = -1.0
        all_results = []

        for pw_int in range(0, 51):  # 0.00 to 0.50
            pw = pw_int / 100.0
            # Renormalize: base shrinks proportionally as pathway grows, so
            # the 5-vector always sums to exactly 1.0 — same constraint
            # SLSQP optimizes under.
            weights = {k: v * (1 - pw) for k, v in base.items()}
            weights["pathway"] = pw

            gene_mrrs = []
            for gene in genes:
                if gene not in scores_cache or scores_cache[gene] is None:
                    continue
                df = scores_cache[gene].copy()

                df["test_score"] = (
                    weights["rna"]     * df["rna_score"]
                    + weights["protein"] * df["protein_score"]
                    + weights["quality"] * df["quality_score"]
                    + weights["context"] * df["context_score"]
                    + weights["pathway"] * df.get("pathway_activity_score", 0.0)
                    + df["geo_confirmation"]
                ).clip(0.0, 1.0)

                # cellosaurus_id is the DataFrame's index (see
                # _precompute_scores' .set_index), not a column — reset_index
                # puts it back as one, matching mrr_score()'s own pattern.
                df = df.sort_values("test_score", ascending=False).reset_index()

                known_cvcls = {
                    name_to_cvcl[n.lower()]
                    for n in VALIDATION_SET[gene]
                    if n.lower() in name_to_cvcl
                }
                if not known_cvcls:
                    continue

                rr = 0.0
                for i, (_, row) in enumerate(df.iterrows(), 1):
                    if row["cellosaurus_id"] in known_cvcls:
                        rr = 1.0 / i
                        break
                gene_mrrs.append(rr)

            mrr = sum(gene_mrrs) / len(gene_mrrs) if gene_mrrs else 0.0
            all_results.append((pw, mrr))

            if mrr > best_mrr:
                best_mrr = mrr
                best_w = pw

            # Print every 5th step + best
            if pw_int % 5 == 0:
                print(f"  {pw:8.2f}  {mrr:.4f}")

        print(f"\n  BEST: pathway_weight={best_w:.2f}, MRR={best_mrr:.4f}")

        all_results_sorted = sorted(all_results, key=lambda x: x[1], reverse=True)
        print(f"  Top 5 weights: "
              f"{[f'{w:.2f}(MRR={m:.4f})' for w, m in all_results_sorted[:5]]}")


if __name__ == "__main__":
    grid_search_pathway_weight()
