from pathlib import Path
import sys
import warnings

import numpy as np
import pandas as pd
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config import CELL_LINE_LOOKUP
from models.classical.pathway_scorer import score_pathway_activity
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

# Optimise five weights (rna/protein/quality/context/pathway); geo bonus
# stays fixed at ±0.10. include_pathway=False (accepted by
# optimise_weights / optimise_weights_by_class / _run_optimisation) drops
# back to just the first four, for a genuinely independent baseline
# comparison against the 5-dimensional result — not the same thing as
# zeroing pathway's weight in a 5D solution, since the other four weights
# would already have been jointly tuned around pathway's presence.
_W_KEYS = ["rna", "protein", "quality", "context", "pathway"]


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

        # Pathway activity — the one component that queries Neo4j. Computed
        # ONCE per gene here (score_pathway_activity has its own
        # gene-keyed cache too), not on every objective-function
        # evaluation during SLSQP: the optimiser below only ever does
        # arithmetic on these already-fetched columns, which is what keeps
        # optimisation tractable despite the extra dimension.
        pathway_df = score_pathway_activity(gene, cell_line_ids=all_cvcl)
        if len(pathway_df) > 0:
            result = result.merge(
                pathway_df[["cellosaurus_id", "pathway_activity_score"]],
                on="cellosaurus_id", how="left",
            )
        else:
            result["pathway_activity_score"] = 0.0
        result["pathway_activity_score"] = result["pathway_activity_score"].fillna(0.0)

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
            + weights.get("pathway", 0.0) * df.get("pathway_activity_score", 0.0)
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


# Canonical 5-D starting points (rna, protein, quality, context, pathway),
# each summing to 1.0. _run_optimisation truncates+renormalises these to 4-D
# when include_pathway=False, so both dimensionalities explore the same
# family of initial guesses rather than unrelated ones. Includes one
# pathway-heavy point (0.40) so SLSQP actually explores a high pathway
# weight from at least one start, not just small perturbations around ~0.10.
_STARTING_POINTS_5D = [
    [0.45,  0.09,  0.225, 0.135, 0.10],   # ~ old default, pathway carved out
    [0.54,  0.09,  0.18,  0.09,  0.10],
    [0.36,  0.18,  0.27,  0.09,  0.10],
    [0.45,  0.045, 0.315, 0.09,  0.10],
    [0.63,  0.045, 0.18,  0.045, 0.10],
    [0.36,  0.09,  0.36,  0.09,  0.10],
    [0.20,  0.10,  0.20,  0.10,  0.40],   # pathway-heavy exploration point
]


def _run_optimisation(
    gene_subset: dict,
    precomputed: dict,
    label: str = "",
    include_pathway: bool = True,
) -> dict:
    """
    SLSQP weight optimisation over a subset of the validation set.

    Scores must already be pre-computed (precomputed dict) — pathway
    scoring already ran inside _precompute_scores, so every objective
    evaluation here is pure arithmetic on cached columns, regardless of
    include_pathway.

    include_pathway=False optimises only rna/protein/quality/context (the
    original 4-D simplex) — a genuinely independent baseline, not a 5-D
    solution with pathway's weight clamped to 0 (which would leave the
    other four weights still shaped by pathway's presence during their
    joint optimisation).

    Returns the best weight dict found.
    """
    keys = _W_KEYS if include_pathway else _W_KEYS[:4]
    n = len(keys)

    if not gene_subset:
        fallback = [0.45, 0.09, 0.225, 0.135, 0.10] if include_pathway else [0.50, 0.10, 0.25, 0.15]
        return dict(zip(keys, fallback))

    def objective(w_arr: np.ndarray) -> float:
        return -mrr_score(dict(zip(keys, w_arr)), gene_subset, precomputed)

    constraints = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]
    bounds = [(0.0, 1.0)] * n

    rng = np.random.default_rng(42)
    starting_points = []
    for pt in _STARTING_POINTS_5D:
        pt = pt[:n]
        starting_points.append((np.array(pt) / sum(pt)).tolist())
    for _ in range(4):
        starting_points.append(rng.dirichlet(np.ones(n)).tolist())

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

    best_weights = dict(zip(keys, best_result.x))
    tag = f" [{label}]" if label else ""
    print(f"\nOptimised weights{tag} (MRR={-best_result.fun:.4f}):")
    for k, v in best_weights.items():
        print(f"  {k}: {v:.4f}")
    return best_weights


def optimise_weights(
    validation_set: dict = VALIDATION_SET,
    include_pathway: bool = True,
) -> dict:
    """
    Maximise MRR on the full validation set via SLSQP with multiple random restarts.

    Scores (including pathway_activity_score, which queries Neo4j once per
    gene) are pre-computed once; the optimiser inner loop is pure
    arithmetic. The geo confirmation bonus stays fixed at ±0.10 (not
    optimised here).

    include_pathway=False optimises the original 4-D simplex
    (rna/protein/quality/context) only — see _run_optimisation's docstring
    for why this isn't the same as a 5-D solution with pathway zeroed.

    Returns the best weight dict found.
    """
    print("Pre-computing validation scores (once)...")
    hpa, ach, gsm = load_mappings()
    precomputed = _precompute_scores(validation_set, hpa, ach, gsm)
    return _run_optimisation(
        validation_set, precomputed, label="all genes", include_pathway=include_pathway
    )


# Pathway weights set from exhaustive grid search (0.00-0.50, step 0.01;
# see scripts/evaluation/pathway_grid_search.py) because SLSQP gets stuck
# at starting points on the step-function MRR surface — confirmed to have
# happened for tissue_specific and ubiquitous (SLSQP reported pathway=0.10
# for both; the grid search found the true optimum near 0.00 for each,
# with MRR falling off from there). Grid search confirmed these trends:
#   tissue_specific:  decreasing (pathway = noise)
#   loss_of_function: increasing (pathway = signal) — MRR was still rising
#                      at the 0.50 edge of the search range, so 0.50 is a
#                      verified FLOOR, not a confirmed peak
#   ubiquitous:       flat/decreasing (pathway ≈ neutral)
_GRID_SEARCH_PATHWAY_WEIGHTS = {
    "tissue_specific":  0.00,
    "ubiquitous":       0.01,
    "loss_of_function": 0.50,
}


def _apply_grid_search_pathway_weights(
    class_weights: dict[str, dict | None],
    classified_genes: dict[str, dict],
    precomputed: dict,
) -> dict[str, dict | None]:
    """
    Replace each class's SLSQP-fitted pathway weight with the grid-search-
    verified optimum (_GRID_SEARCH_PATHWAY_WEIGHTS).

    This does NOT just overwrite the "pathway" key on the SLSQP 5-D
    result — that result's other four weights were fitted jointly with
    SLSQP's own (wrong) pathway value, so a naive overwrite breaks the
    sum-to-1.0 simplex (e.g. loss_of_function: SLSQP's other four weights
    + a swapped-in pathway=0.50 sums to ~1.227, not 1.0). Instead, each
    class's own 4D (no-pathway) baseline is refit and rescaled by
    (1 - pw) — exactly the construction the grid search itself verified,
    so the weights actually applied match what was tested.
    """
    out = dict(class_weights)
    for gene_class, pw in _GRID_SEARCH_PATHWAY_WEIGHTS.items():
        if out.get(gene_class) is None or not classified_genes.get(gene_class):
            continue
        baseline_4d = _run_optimisation(
            classified_genes[gene_class], precomputed,
            label=f"{gene_class} (4D baseline for grid override)",
            include_pathway=False,
        )
        out[gene_class] = {
            **{k: v * (1 - pw) for k, v in baseline_4d.items()},
            "pathway": pw,
        }
    return out


def optimise_weights_by_class(
    validation_set: dict = VALIDATION_SET,
    include_pathway: bool = True,
) -> dict[str, dict | None]:
    """
    Optimise weights SEPARATELY for each gene class.

    When include_pathway=True, each class's pathway weight is NOT the
    SLSQP-fitted value — it's overridden by the grid-search-verified
    optimum; see _apply_grid_search_pathway_weights.

    Returns:
        {
            "tissue_specific": {rna, protein, quality, context, pathway},
            "ubiquitous":      {rna, protein, quality, context, pathway},
            "loss_of_function": None,  # too few validation genes; use tissue_specific weights
        }
        (pathway key omitted from each dict when include_pathway=False)
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
    ts_weights = _run_optimisation(ts_genes, precomputed, label="tissue_specific", include_pathway=include_pathway)

    print("\n=== Optimising ubiquitous weights ===")
    ub_weights = _run_optimisation(ub_genes, precomputed, label="ubiquitous", include_pathway=include_pathway)

    if lof_genes:
        print("\n=== Optimising loss_of_function weights ===")
        lof_weights = _run_optimisation(lof_genes, precomputed, label="loss_of_function", include_pathway=include_pathway)
    else:
        print("\n[loss_of_function] No dedicated LOF-only genes in validation set; skipping.")
        lof_weights = None

    class_weights = {
        "tissue_specific":  ts_weights,
        "ubiquitous":       ub_weights,
        "loss_of_function": lof_weights,
    }

    if include_pathway:
        classified_genes = {
            "tissue_specific": ts_genes, "ubiquitous": ub_genes, "loss_of_function": lof_genes,
        }
        class_weights = _apply_grid_search_pathway_weights(class_weights, classified_genes, precomputed)

    return class_weights
