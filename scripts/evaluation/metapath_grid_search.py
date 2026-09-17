import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from models.classical.ranker import (
    AMPLIFICATION_DRIVEN_GENES,
    WILD_TYPE_MUTATION_PENALTY,
    WILD_TYPE_PREFERRED_GENES,
    _get_learned_weights_by_class,
    _select_class_weights,
    rank,
)
from models.classical.copy_number_scorer import apply_amplification_copy_number_weight
from models.classical.rwr_scorer import apply_rwr_weight
from models.classical.scorer import classify_gene, rank_sort
from models.classical.weights_learned import VALIDATION_SET, _build_name_to_cvcl

# ─────────────────────────────────────────────────────────────────────────────
# Brute-force grid search over JUST the metapath weight, per gene class,
# holding every other weight (rna/protein/quality/context/pathway/mutation/
# copy_number/rwr) at their CURRENT PRODUCTION values — not the un-RWR'd,
# pre-TP53-fix baseline pathway_grid_search.py used. "Current production
# values" means: exactly what ranker.rank()'s own weight-resolution path
# (weights=None, use_learned_weights=True) would compute for that gene
# today — learned per-class weights + grid-verified RWR weight + (for
# MYCN/ERBB2) the amplification copy-number weight — reconstructed here via
# the SAME functions rank() itself calls (_get_learned_weights_by_class,
# apply_rwr_weight, apply_amplification_copy_number_weight), not a
# reimplementation that could drift from what's actually running.
#
# Same renormalization convention as pathway_grid_search.py / every other
# weight decision this project has made: at each candidate metapath weight
# mw, the base vector shrinks proportionally — base_i * (1-mw) — so the
# full vector (including metapath) always sums to exactly 1.0, rather than
# being added on top and silently clipped by final_score's .clip(0,1).
#
# The per-gene component scores (rna_score, ..., metapath_score) are
# fetched ONCE via rank() — the actual production scoring pipeline, same
# justification full_evaluation.py gives for not using weights_learned.py's
# faster-but-separately-maintained internal formula — then the sweep itself
# replicates rank()'s exact final_score arithmetic (both the LOF
# mutation-primary branch and the tissue_specific/ubiquitous branch,
# including the TP53 wild-type penalty and tissue_specific mutation bonus)
# on those cached columns, so 31 weight steps x 44 genes doesn't mean 1,364
# Neo4j/parquet round-trips — only 44.
# ─────────────────────────────────────────────────────────────────────────────

METAPATH_WEIGHTS_TO_TEST = [i / 100.0 for i in range(0, 31)]  # 0.00 .. 0.30


def resolve_production_weights(gene: str) -> dict:
    """
    Exactly mirrors ranker.rank()'s own weight-resolution logic for the
    weights=None, use_learned_weights=True path (production's actual
    behavior) — returns the weights dict rank() would use for this gene,
    with "rwr" already injected and (for amplification-driven genes)
    "copy_number" already injected. Does NOT include "metapath" — that's
    what this grid search adds.
    """
    gene_class = classify_gene(gene)
    if gene_class == "loss_of_function":
        weights = _select_class_weights(_get_learned_weights_by_class(), "loss_of_function")
    else:
        weights = _select_class_weights(_get_learned_weights_by_class(), gene_class)

    if gene in AMPLIFICATION_DRIVEN_GENES and "copy_number" not in weights:
        weights = apply_amplification_copy_number_weight(weights)

    if "rwr" not in weights:
        weights = apply_rwr_weight(weights, gene_class)

    return weights


def compute_test_final_score(df, gene: str, gene_class: str, weights: dict):
    """Exact replica of ranker.rank()'s final_score formula (both branches)."""
    if gene_class == "loss_of_function" and "mutation" in weights:
        final = (
            weights["mutation"] * df["mutation_impact_score"]
            + weights.get("rna", 0.0)     * df["rna_score"]
            + weights.get("protein", 0.0) * df["protein_score"]
            + weights.get("quality", 0.0) * df["quality_score"]
            + weights.get("context", 0.0) * df["context_score"]
            + weights.get("rwr", 0.0)     * df["rwr_score"]
            + weights.get("metapath", 0.0) * df["metapath_score"]
            + df["geo_confirmation"]
        )
    else:
        mutation_bonus = (
            0.05 * df["mutation_impact_score"] if gene_class == "tissue_specific" else 0.0
        )
        wild_type_penalty = (
            WILD_TYPE_MUTATION_PENALTY * df["mutation_impact_score"]
            if gene in WILD_TYPE_PREFERRED_GENES else 0.0
        )
        copy_number_term = (
            weights["copy_number"] * df["copy_number_score"]
            if gene in AMPLIFICATION_DRIVEN_GENES and "copy_number" in weights
            else 0.0
        )
        final = (
            weights["rna"]     * df["rna_score"]
            + weights["protein"] * df["protein_score"]
            + weights["quality"] * df["quality_score"]
            + weights["context"] * df["context_score"]
            + weights.get("pathway", 0.0) * df["pathway_activity_score"]
            + weights.get("rwr", 0.0) * df["rwr_score"]
            + weights.get("metapath", 0.0) * df["metapath_score"]
            + copy_number_term
            + df["geo_confirmation"]
            + mutation_bonus
            - wild_type_penalty
        )
    return final.clip(0.0, 1.0)


def grid_search_metapath_weight():
    name_to_cvcl = _build_name_to_cvcl()

    classified: dict[str, list[str]] = {}
    for gene in VALIDATION_SET:
        classified.setdefault(classify_gene(gene), []).append(gene)

    print("Fetching per-gene component scores ONCE via rank() (the actual "
          "production pipeline) for all 44 validation-set genes...")
    print("(includes the one-time learned-weights warm-up + a Neo4j pathway "
          "query per gene — expect several minutes.)")
    gene_data: dict[str, tuple] = {}
    for i, gene in enumerate(VALIDATION_SET, 1):
        print(f"  [{i}/{len(VALIDATION_SET)}] {gene}...")
        df = rank(gene, top_n=None, weights=None, use_learned_weights=True,
                   include_pathway=True)
        if df is None or len(df) == 0:
            print(f"    WARNING: no data for {gene}, skipping")
            continue
        base_weights = resolve_production_weights(gene)
        gene_data[gene] = (df, base_weights)

    print()
    print("=" * 60)
    print("METAPATH WEIGHT GRID SEARCH BY GENE CLASS")
    print("=" * 60)

    per_class_best = {}

    for gene_class, genes in classified.items():
        genes = [g for g in genes if g in gene_data]
        if not genes:
            continue

        print(f"\n--- {gene_class} ({len(genes)} genes) ---")
        # Report the production base (from the FIRST gene in this class —
        # same base shape for every gene of this class, except LOF's
        # gene-specific mutation-primary vector, which is identical across
        # LOF genes too since they all share the class-level fit).
        print(f"Base weights (current production, incl. rwr): "
              f"{gene_data[genes[0]][1]}")
        print(f"{'metapath_w':>10s} {'MRR':>8s}")
        print("-" * 50)

        best_w, best_mrr = 0.0, -1.0
        all_results = []

        for mw in METAPATH_WEIGHTS_TO_TEST:
            gene_mrrs = []
            for gene in genes:
                df, base = gene_data[gene]
                weights = {k: v * (1 - mw) for k, v in base.items()}
                weights["metapath"] = mw

                test_df = df.copy()
                test_df["test_score"] = compute_test_final_score(
                    test_df, gene, gene_class, weights
                )
                test_df = rank_sort(test_df, "test_score")

                known_cvcls = {
                    name_to_cvcl[n.lower()]
                    for n in VALIDATION_SET[gene]
                    if n.lower() in name_to_cvcl
                }
                if not known_cvcls:
                    continue

                rr = 0.0
                for i, (_, row) in enumerate(test_df.iterrows(), 1):
                    if row["cellosaurus_id"] in known_cvcls:
                        rr = 1.0 / i
                        break
                gene_mrrs.append(rr)

            mrr = sum(gene_mrrs) / len(gene_mrrs) if gene_mrrs else 0.0
            all_results.append((mw, mrr))
            if mrr > best_mrr:
                best_mrr, best_w = mrr, mw
            if round(mw * 100) % 5 == 0:
                print(f"  {mw:8.2f}  {mrr:.4f}")

        baseline_mrr = dict(all_results)[0.0]
        print(f"\n  Baseline (metapath=0.00): MRR={baseline_mrr:.4f}")
        print(f"  BEST: metapath_weight={best_w:.2f}, MRR={best_mrr:.4f} "
              f"(delta={best_mrr - baseline_mrr:+.4f})")
        all_sorted = sorted(all_results, key=lambda x: x[1], reverse=True)
        print(f"  Top 5 weights: "
              f"{[f'{w:.2f}(MRR={m:.4f})' for w, m in all_sorted[:5]]}")

        per_class_best[gene_class] = {
            "best_weight": best_w, "best_mrr": best_mrr,
            "baseline_mrr": baseline_mrr, "delta": best_mrr - baseline_mrr,
        }

    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for cls, r in per_class_best.items():
        print(f"  {cls:18s}  baseline={r['baseline_mrr']:.4f}  "
              f"best={r['best_mrr']:.4f} @ w={r['best_weight']:.2f}  "
              f"delta={r['delta']:+.4f}")

    return per_class_best


if __name__ == "__main__":
    grid_search_metapath_weight()
