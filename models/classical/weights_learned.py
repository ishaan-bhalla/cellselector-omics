from pathlib import Path
import sys
import warnings

import numpy as np
import pandas as pd
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config import CELL_LINE_LOOKUP
from models.classical.scorer import (
    classify_gene,
    load_mappings,
    score_context,
    score_data_quality,
    score_protein_expression,
    score_rna_expression,
)

VALIDATION_SET = {
    # EGFR family
    "EGFR":  ["HCC827", "NCI-H3255", "A-431", "NCI-H1975", "PC-9"],
    "ERBB2": ["SK-BR-3", "AU565", "BT-474", "JIMT-1", "HCC1954"],
    "ERBB3": ["MCF-7", "T-47D"],

    # Tumor suppressors
    "TP53":  ["HCT116", "U-2 OS", "MCF-7"],
    "BRCA1": ["HCC1937", "MDA-MB-436", "SUM149PT"],
    "BRCA2": ["CAPAN-1", "CFPAC-1"],
    "RB1":   ["WERI-Rb-1", "Y79"],

    # Oncogenes
    "KRAS":  ["SW620", "CALU-1", "NCI-H441"],
    "BRAF":  ["A375", "SK-MEL-28", "COLO 205"],
    "MYC":   ["HL-60", "Daudi", "Raji"],
    "MYCN":  ["IMR-32", "Kelly", "SK-N-BE(2)"],
    "MET":   ["EBC-1", "Hs 746T", "SNU-5"],
    "KIT":   ["Kasumi-1", "GIST882", "HMC-1"],
    "ALK":   ["NCI-H2228", "KARPAS-299"],
    "RET":   ["TT", "MZ-CRC-1"],

    # Hormone receptors
    "ESR1":  ["MCF-7", "T-47D", "ZR-75-1"],
    "AR":    ["LNCaP", "22Rv1", "VCaP"],
    "PGR":   ["T-47D", "BT-474"],

    # Immune checkpoints
    "CD274": ["NCI-H226", "Hs 695T"],

    # Metabolism
    "IDH1":  ["HT-1080", "U-87 MG"],
    "IDH2":  ["TF-1", "Kasumi-1"],

    # DNA repair
    "ATM":   ["SKW6.4", "BL-2"],
    "PARP1": ["MCF-7", "HeLa"],

    # Cell cycle
    "CDK4":  ["COLO 800", "NCI-H460"],
    "CCND1": ["MCF-7", "SK-BR-3"],
}

# Optimise only the four main weights; geo bonus stays fixed at ±0.10
_W_KEYS = ["rna", "protein", "quality", "context"]


def _build_name_to_cvcl() -> dict:
    """Comprehensive cell-line-name → cellosaurus_id lookup."""
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
    """Pre-compute all component scores for the validation set (run once)."""
    scores: dict = {}
    for gene in validation_set:
        print(f"  Pre-computing {gene}...")
        gc     = classify_gene(gene)
        rna_df = score_rna_expression(gene, hpa_to_cvcl, gsm_to_cvcl,
                                      gene_class=gc)
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
        result["rna_score"]        = result["rna_score"].fillna(0.0)
        result["protein_score"]    = result["protein_score"].fillna(0.0)
        result["geo_confirmation"] = result["geo_confirmation"].fillna(0.0)

        quality_df = score_data_quality(all_cvcl, rna_df, protein_df)
        result = result.merge(quality_df, on="cellosaurus_id", how="left")
        result["quality_score"] = result["quality_score"].fillna(0.0)

        # Context without filter: context_score = 0 for all rows.
        # This means the context weight cannot be tuned from MRR alone,
        # but it is included to keep the weight simplex intact.
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
    """Mean Reciprocal Rank across the validation set. Higher = better."""
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
            weights["rna"]     * df["rna_score"]
            + weights["protein"] * df["protein_score"]
            + weights["quality"] * df["quality_score"]
            + weights["context"] * df["context_score"]
            + df["geo_confirmation"]   # fixed additive, not optimised
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


def _run_optimisation(
    gene_subset: dict,
    precomputed: dict,
    label: str = "",
) -> dict:
    """
    SLSQP weight optimisation over a subset of the validation set.

    Scores must already be pre-computed (precomputed dict).
    Returns the best weight dict found.
    """
    if not gene_subset:
        return dict(zip(_W_KEYS, [0.50, 0.10, 0.25, 0.15]))

    def objective(w_arr: np.ndarray) -> float:
        return -mrr_score(dict(zip(_W_KEYS, w_arr)), gene_subset, precomputed)

    constraints = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
    bounds = [(0.0, 1.0)] * 4

    rng = np.random.default_rng(42)
    starting_points = [
        [0.50, 0.10, 0.25, 0.15],
        [0.60, 0.10, 0.20, 0.10],
        [0.40, 0.20, 0.30, 0.10],
        [0.50, 0.05, 0.35, 0.10],
        [0.70, 0.05, 0.20, 0.05],
        [0.40, 0.10, 0.40, 0.10],
    ]
    for _ in range(4):
        starting_points.append(rng.dirichlet(np.ones(4)).tolist())

    best_result = None
    for x0 in starting_points:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = minimize(
                objective, x0, method="SLSQP",
                bounds=bounds, constraints=constraints,
                options={"ftol": 1e-8, "maxiter": 400},
            )
        if best_result is None or res.fun < best_result.fun:
            best_result = res

    best_weights = dict(zip(_W_KEYS, best_result.x))
    tag = f" [{label}]" if label else ""
    print(f"\nOptimised weights{tag} (MRR={-best_result.fun:.4f}):")
    for k, v in best_weights.items():
        print(f"  {k}: {v:.4f}")
    return best_weights


def optimise_weights(validation_set: dict = VALIDATION_SET) -> dict:
    """
    Maximise MRR on the full validation set via SLSQP with multiple random restarts.

    Scores are pre-computed once; the optimiser inner loop is pure arithmetic.
    The geo confirmation bonus stays fixed at ±0.10 (not optimised here).

    Returns the best weight dict found.
    """
    print("Pre-computing validation scores (once)...")
    hpa, ach, gsm = load_mappings()
    precomputed = _precompute_scores(validation_set, hpa, ach, gsm)
    return _run_optimisation(validation_set, precomputed, label="all genes")


def optimise_weights_by_class(
    validation_set: dict = VALIDATION_SET,
) -> dict[str, dict | None]:
    """
    Optimise weights SEPARATELY for each gene class.

    Returns:
        {
            "tissue_specific": {rna, protein, quality, context},
            "ubiquitous":      {rna, protein, quality, context},
            "loss_of_function": None,  # too few validation genes; use tissue_specific weights
        }
    """
    print("Pre-computing all validation scores (once)...")
    hpa, ach, gsm = load_mappings()
    precomputed = _precompute_scores(validation_set, hpa, ach, gsm)

    ts_genes  = {g: v for g, v in validation_set.items() if classify_gene(g) == "tissue_specific"}
    ub_genes  = {g: v for g, v in validation_set.items() if classify_gene(g) == "ubiquitous"}
    lof_genes = {g: v for g, v in validation_set.items() if classify_gene(g) == "loss_of_function"}

    print(f"\nGene class split — tissue_specific: {len(ts_genes)}, "
          f"ubiquitous: {len(ub_genes)}, loss_of_function: {len(lof_genes)}")

    print("\n=== Optimising tissue_specific weights ===")
    ts_weights = _run_optimisation(ts_genes, precomputed, label="tissue_specific")

    print("\n=== Optimising ubiquitous weights ===")
    ub_weights = _run_optimisation(ub_genes, precomputed, label="ubiquitous")

    if lof_genes:
        print("\n=== Optimising loss_of_function weights ===")
        lof_weights = _run_optimisation(lof_genes, precomputed, label="loss_of_function")
    else:
        print("\n[loss_of_function] No dedicated LOF-only genes in validation set; skipping.")
        lof_weights = None

    return {
        "tissue_specific":  ts_weights,
        "ubiquitous":       ub_weights,
        "loss_of_function": lof_weights,
    }
