import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config import OUTPUTS_DIR
from scripts.evaluation.compare_ranking_methods import _aligned_rrs, paired_bootstrap_test

# ─────────────────────────────────────────────────────────────────────────────
# Paired bootstrap significance test: Production+RWR+Metapath (Config D) vs
# Production+RWR (Config C, current baseline, LOO-CV MRR=0.2367) — same
# paired_bootstrap_test (10,000 resamples) this project already uses for
# every other significance claim (RRF/LambdaMART vs baseline), reused
# as-is rather than reimplemented, on the per-gene RR arrays
# metapath_cross_validated_evaluation.py just saved.
# ─────────────────────────────────────────────────────────────────────────────

RESULTS_PATH = OUTPUTS_DIR / "metapath_cross_validated_loo_results.json"


def run():
    with open(RESULTS_PATH) as f:
        results = json.load(f)

    per_gene_c = results["per_gene_rr"]["C"]
    per_gene_d = results["per_gene_rr"]["D"]
    gene_classes = results["gene_classes"]

    print("=" * 60)
    print("OVERALL (44 genes): Production+RWR+Metapath (D) vs Production+RWR (C)")
    print("=" * 60)
    genes, rrs_d, rrs_c = _aligned_rrs(per_gene_d, per_gene_c)
    diff, p_val, (ci_lo, ci_hi) = paired_bootstrap_test(rrs_d, rrs_c)
    sig = "SIGNIFICANT" if p_val < 0.05 and not (ci_lo <= 0 <= ci_hi) else "NOT significant"
    print(f"  n = {len(genes)} genes")
    print(f"  Config C (Production+RWR) MRR:          {sum(rrs_c)/len(rrs_c):.4f}")
    print(f"  Config D (Production+RWR+Metapath) MRR: {sum(rrs_d)/len(rrs_d):.4f}")
    print(f"  Observed diff (D - C): {diff:+.4f}")
    print(f"  p-value: {p_val:.4f}")
    print(f"  95% CI on diff: [{ci_lo:+.4f}, {ci_hi:+.4f}]")
    print(f"  --> {sig} at alpha=0.05")

    print()
    print("=" * 60)
    print("PER-CLASS BREAKDOWN (same test, restricted to each class's genes)")
    print("=" * 60)
    for cls in ("tissue_specific", "ubiquitous", "loss_of_function"):
        cls_genes = [g for g in genes if gene_classes.get(g) == cls]
        if len(cls_genes) < 2:
            print(f"  {cls}: too few genes ({len(cls_genes)}) for a meaningful bootstrap, skipping")
            continue
        rrs_d_cls = [per_gene_d[g] for g in cls_genes]
        rrs_c_cls = [per_gene_c[g] for g in cls_genes]
        diff_c, p_c, (lo_c, hi_c) = paired_bootstrap_test(rrs_d_cls, rrs_c_cls)
        sig_c = "SIGNIFICANT" if p_c < 0.05 and not (lo_c <= 0 <= hi_c) else "NOT significant"
        print(f"  {cls:18s} (n={len(cls_genes):2d}): diff={diff_c:+.4f}  p={p_c:.4f}  "
              f"CI=[{lo_c:+.4f}, {hi_c:+.4f}]  --> {sig_c}")

    return {
        "overall": {"diff": diff, "p_value": p_val, "ci": [ci_lo, ci_hi], "n": len(genes)},
    }


if __name__ == "__main__":
    run()
