from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config import OUTPUTS_DIR
from models.classical.ranker import FIXED_WEIGHTS, rank
from models.classical.weights_learned import (
    VALIDATION_SET,
    _build_name_to_cvcl,
    optimise_weights,
)


def _compute_mrr(results_by_gene: dict, name_to_cvcl: dict) -> float:
    all_rr: list[float] = []
    for gene, (results, known_names) in results_by_gene.items():
        if results is None or len(results) == 0:
            continue
        known_cvcls = {name_to_cvcl.get(n.lower()) for n in known_names} - {None}
        for cvcl in known_cvcls:
            hits = results.index[results["cellosaurus_id"] == cvcl].tolist()
            all_rr.append(1.0 / (hits[0] + 1) if hits else 0.0)
    return float(np.mean(all_rr)) if all_rr else 0.0


def _hit_rate(results_by_gene: dict, name_to_cvcl: dict, k: int) -> float:
    if not results_by_gene:
        return 0.0
    hits = 0
    for gene, (results, known_names) in results_by_gene.items():
        if results is None or len(results) == 0:
            continue
        known_cvcls = {name_to_cvcl.get(n.lower()) for n in known_names} - {None}
        top_k = set(results.head(k)["cellosaurus_id"])
        if known_cvcls & top_k:
            hits += 1
    return hits / len(results_by_gene)


def evaluate_both() -> dict:
    """Compare FIXED_WEIGHTS vs LEARNED_WEIGHTS on the validation gene set."""
    name_to_cvcl = _build_name_to_cvcl()

    print("=== Optimising weights ===")
    learned_weights = optimise_weights(VALIDATION_SET)

    print("\n=== Ranking with FIXED weights ===")
    fixed_results: dict = {}
    for gene, known_names in VALIDATION_SET.items():
        print(f"  {gene}...")
        fixed_results[gene] = (rank(gene, top_n=None, weights=FIXED_WEIGHTS), known_names)

    print("\n=== Ranking with LEARNED weights ===")
    learned_results: dict = {}
    for gene, known_names in VALIDATION_SET.items():
        print(f"  {gene}...")
        learned_results[gene] = (rank(gene, top_n=None, weights=learned_weights), known_names)

    fixed_mrr    = _compute_mrr(fixed_results,   name_to_cvcl)
    learned_mrr  = _compute_mrr(learned_results, name_to_cvcl)
    fixed_hr5    = _hit_rate(fixed_results,   name_to_cvcl, k=5)
    fixed_hr10   = _hit_rate(fixed_results,   name_to_cvcl, k=10)
    learned_hr5  = _hit_rate(learned_results, name_to_cvcl, k=5)
    learned_hr10 = _hit_rate(learned_results, name_to_cvcl, k=10)

    print("\n" + "=" * 60)
    print("EVALUATION RESULTS")
    print("=" * 60)
    print(f"{'Metric':<25} {'FIXED':>10} {'LEARNED':>10}")
    print("-" * 47)
    print(f"{'MRR':<25} {fixed_mrr:>10.4f} {learned_mrr:>10.4f}")
    print(f"{'Hit rate @5':<25} {fixed_hr5:>10.4f} {learned_hr5:>10.4f}")
    print(f"{'Hit rate @10':<25} {fixed_hr10:>10.4f} {learned_hr10:>10.4f}")

    print(f"\n{'Gene':<8} {'Known line':<22} {'Fixed rank':>12} {'Learned rank':>13}")
    print("-" * 57)
    for gene, known_names in VALIDATION_SET.items():
        fixed_r,   _ = fixed_results[gene]
        learned_r, _ = learned_results[gene]
        for name in known_names:
            cvcl = name_to_cvcl.get(name.lower())
            if cvcl and fixed_r is not None and len(fixed_r) > 0:
                fi = fixed_r.index[fixed_r["cellosaurus_id"] == cvcl].tolist()
                li = learned_r.index[learned_r["cellosaurus_id"] == cvcl].tolist()
                fr = fi[0] + 1 if fi else ">all"
                lr = li[0] + 1 if li else ">all"
            else:
                fr = lr = "not found"
            print(f"{gene:<8} {name:<22} {str(fr):>12} {str(lr):>13}")

    winner = "LEARNED" if learned_mrr > fixed_mrr else "FIXED"
    delta  = abs(learned_mrr - fixed_mrr)
    print(f"\n→ {winner} weights win  (delta MRR: {delta:.4f})")
    print(f"  Learned: {learned_weights}")

    output = {
        "fixed_weights":          FIXED_WEIGHTS,
        "learned_weights":        {k: float(v) for k, v in learned_weights.items()},
        "fixed_mrr":              fixed_mrr,
        "learned_mrr":            learned_mrr,
        "fixed_hit_rate_at_5":    fixed_hr5,
        "fixed_hit_rate_at_10":   fixed_hr10,
        "learned_hit_rate_at_5":  learned_hr5,
        "learned_hit_rate_at_10": learned_hr10,
        "winner":                 winner,
    }
    out_path = OUTPUTS_DIR / "model_evaluation.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved → {out_path}")

    return output


if __name__ == "__main__":
    evaluate_both()
