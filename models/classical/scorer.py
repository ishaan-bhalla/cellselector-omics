from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config import (
    CELL_LINE_LOOKUP,
    GEO_INFO,
    MASTER_CONFIDENCE,
    PARQUET_DIR,
    SAMPLE_INFO,
)

FIXED_WEIGHTS = {
    "rna":     0.50,
    "protein": 0.10,
    "quality": 0.25,
    "context": 0.15,
}

# GEO confirmation bonus/penalty — additive, not part of weighted sum
GEO_BONUS   = +0.10
GEO_PENALTY = -0.10

GENE_CLASSES: dict[str, list[str]] = {
    "ubiquitous": [
        "TP53", "PARP1", "CDK4", "CCND1", "ACTB",
        "GAPDH", "RB1", "ATM", "BRCA1", "BRCA2",
        "MDM2", "CDK2", "CDK6", "PCNA", "MKI67",
    ],
    "loss_of_function": [
        "BRCA1", "BRCA2", "RB1", "ATM", "PTEN",
        "APC", "VHL", "MLH1", "MSH2", "TP53",
    ],
}

GENE_ROLES: dict[str, str] = {
    # Receptor tyrosine kinases
    "EGFR":   "receptor tyrosine kinase",
    "ERBB2":  "receptor tyrosine kinase (HER2)",
    "ERBB3":  "receptor tyrosine kinase (HER3)",
    "MET":    "receptor tyrosine kinase",
    "KIT":    "receptor tyrosine kinase",
    "ALK":    "receptor tyrosine kinase",
    "RET":    "receptor tyrosine kinase",
    "FLT3":   "receptor tyrosine kinase",
    "PDGFRA": "receptor tyrosine kinase",
    # Hormone receptors
    "ESR1": "estrogen receptor",
    "AR":   "androgen receptor",
    "PGR":  "progesterone receptor",
    # Immune checkpoint / surface markers
    "CD274": "immune checkpoint marker (PD-L1)",
    "PDCD1": "immune checkpoint marker (PD-1)",
    "CTLA4": "immune checkpoint marker",
    # Tumor suppressors
    "TP53":  "tumor suppressor",
    "RB1":   "tumor suppressor",
    "PTEN":  "tumor suppressor",
    "BRCA1": "tumor suppressor (DNA repair)",
    "BRCA2": "tumor suppressor (DNA repair)",
    "APC":   "tumor suppressor",
    "VHL":   "tumor suppressor",
    # Oncogenes / signaling
    "KRAS":   "oncogene (RAS family GTPase)",
    "BRAF":   "oncogene (kinase)",
    "MYC":    "oncogene (transcription factor)",
    "MYCN":   "oncogene (transcription factor)",
    "PIK3CA": "oncogene (kinase)",
    # Proliferation markers
    "MKI67": "proliferation marker (Ki-67)",
    "PCNA":  "proliferation marker",
}


def get_gene_role(gene: str) -> str | None:
    return GENE_ROLES.get(gene.upper())


def classify_gene(gene: str) -> str:
    if gene in GENE_CLASSES["loss_of_function"]:
        return "loss_of_function"
    if gene in GENE_CLASSES["ubiquitous"]:
        return "ubiquitous"
    return "tissue_specific"


def load_mappings() -> tuple[dict, dict, dict]:
    """Return (hpa_to_cvcl, ach_to_cvcl, gsm_to_cvcl)."""
    lkp = pd.read_parquet(CELL_LINE_LOOKUP, columns=["cellosaurus_id", "hpa_name"])
    hpa_to_cvcl = dict(zip(lkp["hpa_name"].dropna(), lkp["cellosaurus_id"].dropna()))

    samp = pd.read_csv(SAMPLE_INFO, usecols=["DepMap_ID", "RRID"], low_memory=False)
    ach_to_cvcl = {r.DepMap_ID: r.RRID for r in samp.itertuples() if pd.notna(r.RRID)}

    geo = pd.read_csv(
        GEO_INFO, sep="\t",
        usecols=["Geo_accession", "Cellosaurus_ID"],
        low_memory=False,
    )
    gsm_to_cvcl = dict(
        zip(geo["Geo_accession"].dropna(), geo["Cellosaurus_ID"].dropna())
    )

    return hpa_to_cvcl, ach_to_cvcl, gsm_to_cvcl


def _pct_rank(series: pd.Series) -> np.ndarray:
    return series.rank(pct=True, method="average").values


# ─────────────────────────────────────────────────────────────────────────────
# PRIMARY RNA SCORING  (HPA + DepMap)
# GEO is computed separately and returned as a ±0.10 confirmation signal
# ─────────────────────────────────────────────────────────────────────────────

def score_rna_expression(
    gene: str,
    hpa_to_cvcl: dict,
    gsm_to_cvcl: dict,
    gene_class: str | None = None,
) -> pd.DataFrame:
    """
    Score RNA expression for a gene across all cell lines.

    HPA + DepMap are the primary sources (equal weight when both present).
    GEO acts as a confirmation signal only (±0.10 additive bonus, not mixed
    into the percentile ranking).

    gene_class controls the RNA scoring strategy:
      - "tissue_specific" / None  →  rna_score = mean(hpa_rank, depmap_rank)
      - "ubiquitous"              →  rna_score = 1 - CV(hpa_rank, depmap_rank)
                                      where CV = |h-d| / (h+d)
                                      (consistency beats expression level)
      - "loss_of_function"        →  same as tissue_specific
                                      (caller adds LOF flag in the result)

    Returns columns:
        cellosaurus_id, rna_score, hpa_score, depmap_score,
        n_primary_sources, missing_data_flag,
        geo_confirmation, geo_n_samples
    """
    _empty = pd.DataFrame(
        columns=[
            "cellosaurus_id", "rna_score", "hpa_score", "depmap_score",
            "n_primary_sources", "missing_data_flag",
            "geo_confirmation", "geo_n_samples",
        ]
    )

    # ── HPA: nTPM only, threshold > 1 ────────────────────────────────────────
    hpa_raw = pd.read_parquet(
        PARQUET_DIR / "gene_expr_hpa_preprocessed.parquet",
        filters=[("gene_symbol", "=", gene), ("units", "=", "nTPM")],
        columns=["original_id", "expression_value"],
    )
    hpa_df = pd.DataFrame(columns=["cellosaurus_id", "hpa_score"])
    if len(hpa_raw) > 0:
        agg = hpa_raw.groupby("original_id", observed=True)["expression_value"].mean()
        agg = agg[agg > 1.0]
        if len(agg) > 0:
            cvcl = agg.index.map(hpa_to_cvcl)
            mask = cvcl.notna()
            hpa_df = (
                pd.DataFrame({
                    "cellosaurus_id": cvcl[mask].values,
                    "hpa_score": _pct_rank(agg[mask]),
                })
                .groupby("cellosaurus_id")["hpa_score"].mean()
                .reset_index()
            )

    # ── DepMap: TPM_log1p, threshold > 0.5 ───────────────────────────────────
    dep_raw = pd.read_parquet(
        PARQUET_DIR / "gene_expr_depmap_preprocessed.parquet",
        filters=[("gene_symbol", "=", gene)],
        columns=["cellosaurus_id", "expression_value"],
    )
    dep_df = pd.DataFrame(columns=["cellosaurus_id", "depmap_score"])
    if len(dep_raw) > 0:
        dep_raw = dep_raw.dropna(subset=["cellosaurus_id"])
        dep_raw = dep_raw[dep_raw["expression_value"] > 0.5]
        if len(dep_raw) > 0:
            agg = dep_raw.groupby("cellosaurus_id", observed=True)["expression_value"].mean()
            dep_df = pd.DataFrame({
                "cellosaurus_id": agg.index.astype(str),
                "depmap_score": _pct_rank(agg),
            })

    # ── GEO: confirmation signal only ────────────────────────────────────────
    # Multiple GSMs per cell line → take median; CV = std/|median|
    geo_raw = pd.read_parquet(
        PARQUET_DIR / "gene_expr_geo_preprocessed.parquet",
        filters=[("gene_symbol", "=", gene)],
        columns=["original_id", "expression_value"],
    )
    geo_df = pd.DataFrame(columns=["cellosaurus_id", "geo_expressed", "geo_cv", "geo_n_samples"])
    if len(geo_raw) > 0:
        geo_raw["cellosaurus_id"] = geo_raw["original_id"].map(gsm_to_cvcl)
        geo_raw = geo_raw.dropna(subset=["cellosaurus_id"])
        if len(geo_raw) > 0:
            g = geo_raw.groupby("cellosaurus_id")["expression_value"]
            med = g.median()
            std = g.std().fillna(0.0)
            n   = g.count()
            cv  = (std / med.abs().clip(lower=1e-9)).clip(upper=10.0)
            geo_df = pd.DataFrame({
                "cellosaurus_id": med.index,
                "geo_median":     med.values,
                "geo_cv":         cv.values,
                "geo_n_samples":  n.values,
                "geo_expressed":  ((med.values > 0) & (cv.values < 0.5)),
            })

    # ── Merge primary sources ─────────────────────────────────────────────────
    all_cvcl = set(hpa_df["cellosaurus_id"]) | set(dep_df["cellosaurus_id"])
    if not all_cvcl:
        return _empty

    result = (
        pd.DataFrame({"cellosaurus_id": list(all_cvcl)})
        .merge(hpa_df, on="cellosaurus_id", how="left")
        .merge(dep_df, on="cellosaurus_id", how="left")
    )

    # Combine HPA and DepMap; strategy depends on gene_class
    def _rna(row):
        h, d = row["hpa_score"], row["depmap_score"]
        has_h, has_d = pd.notna(h), pd.notna(d)
        if gene_class == "ubiquitous":
            if has_h and has_d:
                # Cross-source consistency: 1 - |h-d|/(h+d)
                denom = float(h) + float(d)
                cv = abs(float(h) - float(d)) / denom if denom > 0 else 0.0
                return 1.0 - cv, 2, False
            elif has_h or has_d:
                return 0.5, 1, False   # neutral: can't assess consistency
            return 0.0, 0, True
        else:
            # tissue_specific and loss_of_function: percentile-rank average
            if has_h and has_d:
                return 0.5 * float(h) + 0.5 * float(d), 2, False
            elif has_h:
                return float(h), 1, False
            elif has_d:
                return float(d), 1, False
            return 0.0, 0, True   # flagged: no primary data

    tmp = result.apply(_rna, axis=1, result_type="expand")
    result["rna_score"]         = tmp[0]
    result["n_primary_sources"] = tmp[1].astype(int)
    result["missing_data_flag"] = tmp[2]

    # ── GEO confirmation bonus / penalty ─────────────────────────────────────
    result = result.merge(
        geo_df[["cellosaurus_id", "geo_expressed", "geo_n_samples"]],
        on="cellosaurus_id", how="left",
    )

    def _geo_conf(row):
        if pd.isna(row["geo_n_samples"]):
            return 0.0                               # no GEO data → neutral
        if row["geo_expressed"]:
            return GEO_BONUS                         # GEO confirms expression
        elif row["rna_score"] > 0:
            return GEO_PENALTY                       # GEO contradicts primary
        return 0.0                                   # both say absent → neutral

    result["geo_confirmation"] = result.apply(_geo_conf, axis=1)

    return result[[
        "cellosaurus_id", "rna_score", "hpa_score", "depmap_score",
        "n_primary_sources", "missing_data_flag",
        "geo_confirmation", "geo_n_samples",
    ]]


def score_protein_expression(gene: str, ach_to_cvcl: dict) -> pd.DataFrame:
    """
    Percentile-rank protein expression from CCLE MS proteomics.
    No threshold — MS intensity scale is different from RNA.

    Returns columns: cellosaurus_id, protein_score
    """
    prot_raw = pd.read_parquet(
        PARQUET_DIR / "gene_expr_ccle_proteomics_preprocessed.parquet",
        filters=[("gene_symbol", "=", gene)],
        columns=["original_id", "expression_value"],
    )
    if len(prot_raw) == 0:
        return pd.DataFrame(columns=["cellosaurus_id", "protein_score"])

    prot_raw["cellosaurus_id"] = prot_raw["original_id"].map(ach_to_cvcl)
    prot_raw = prot_raw.dropna(subset=["cellosaurus_id"])
    if len(prot_raw) == 0:
        return pd.DataFrame(columns=["cellosaurus_id", "protein_score"])

    agg = prot_raw.groupby("cellosaurus_id")["expression_value"].mean()
    return pd.DataFrame({"cellosaurus_id": agg.index, "protein_score": _pct_rank(agg)})


# ─────────────────────────────────────────────────────────────────────────────
# CRISPR DEPENDENCY SCORING (DepMap)
# Gene ESSENTIALITY, not expression — kept as a separate evidence column,
# never mixed into the weighted final_score (see ranker.rank()).
# ─────────────────────────────────────────────────────────────────────────────

def score_crispr_dependency(gene: str) -> pd.DataFrame:
    """
    Load CRISPR dependency scores for a gene.

    High dependency = gene is essential for that cell line's survival —
    a different signal from high expression (a gene can be highly expressed
    without being essential, and vice versa).

    Returns columns: cellosaurus_id, dependency_score, dependency_percentile
    """
    _empty = pd.DataFrame(
        columns=["cellosaurus_id", "dependency_score", "dependency_percentile"]
    )

    import os as _os
    if not _os.path.exists(PARQUET_DIR / "crispr_dependency_depmap_preprocessed.parquet"):
        return _empty
    crispr_raw = pd.read_parquet(
        PARQUET_DIR / "crispr_dependency_depmap_preprocessed.parquet",
        filters=[("gene_symbol", "=", gene)],
        columns=["cellosaurus_id", "dependency_score"],
    )
    crispr_raw = crispr_raw.dropna(subset=["cellosaurus_id"])
    if len(crispr_raw) == 0:
        return _empty

    agg = crispr_raw.groupby("cellosaurus_id")["dependency_score"].mean()
    return pd.DataFrame({
        "cellosaurus_id":         agg.index,
        "dependency_score":       agg.values,
        "dependency_percentile":  _pct_rank(agg),
    })


def score_data_quality(
    cellosaurus_ids,
    rna_df: pd.DataFrame,
    protein_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Data quality score per cell line.

    quality = 0.40*(n_primary_sources/2)
            + 0.40*(1 - cross_source_std_HPA_DepMap)
            + 0.20*completeness

    cross_source_std is between HPA and DepMap only (GEO excluded — units unknown).

    Returns columns: cellosaurus_id, quality_score, n_sources,
                     cross_source_std, completeness
    """
    conf = pd.read_parquet(MASTER_CONFIDENCE, columns=["cellosaurus_id", "confidence"])

    rna_cols = ["cellosaurus_id", "n_primary_sources", "hpa_score", "depmap_score"]
    rna_sub  = rna_df[[c for c in rna_cols if c in rna_df.columns]]

    result = (
        pd.DataFrame({"cellosaurus_id": list(cellosaurus_ids)})
        .merge(rna_sub, on="cellosaurus_id", how="left")
        .merge(conf, on="cellosaurus_id", how="left")
    )
    for col in ["n_primary_sources", "hpa_score", "depmap_score"]:
        if col not in result.columns:
            result[col] = np.nan

    # std between HPA and DepMap only — NaN if either missing (then =0)
    result["cross_source_std"] = (
        result[["hpa_score", "depmap_score"]]
        .std(axis=1, skipna=True)
        .fillna(0.0)
    )
    result["n_sources"]    = result["n_primary_sources"].fillna(0.0)
    result["completeness"] = result["confidence"].fillna(0.0)

    result["quality_score"] = (
        0.40 * (result["n_sources"] / 2.0)        # /2 = two primary sources
        + 0.40 * (1.0 - result["cross_source_std"])
        + 0.20 * result["completeness"]
    )

    return result[["cellosaurus_id", "quality_score", "n_sources",
                   "cross_source_std", "completeness"]]


def score_context(
    cellosaurus_ids,
    disease_filter: str | None = None,
    lineage_filter: str | None = None,
) -> pd.DataFrame:
    """
    Context relevance score.

    disease_match: 1.0 exact, 0.5 partial (substring), 0.0 none
    lineage_match: 1.0 match, 0.0 none
    context_score = max(disease_match, lineage_match)

    Returns columns: cellosaurus_id, context_score, disease, lineage
    """
    lkp = pd.read_parquet(
        CELL_LINE_LOOKUP, columns=["cellosaurus_id", "disease", "lineage"]
    )
    result = (
        pd.DataFrame({"cellosaurus_id": list(cellosaurus_ids)})
        .merge(lkp, on="cellosaurus_id", how="left")
    )

    def _dmatch(val: str | float) -> float:
        if not pd.notna(val) or not val:
            return 0.0
        v, f = str(val).lower().strip(), disease_filter.lower().strip()
        if v == f:
            return 1.0
        return 0.5 if (f in v or v in f) else 0.0

    def _lmatch(val: str | float) -> float:
        if not pd.notna(val) or not val:
            return 0.0
        v, f = str(val).lower().strip(), lineage_filter.lower().strip()
        return 1.0 if (f in v or v == f) else 0.0

    result["disease_match"] = (
        result["disease"].apply(_dmatch) if disease_filter else 0.0
    )
    result["lineage_match"] = (
        result["lineage"].apply(_lmatch) if lineage_filter else 0.0
    )
    result["context_score"] = result[["disease_match", "lineage_match"]].max(axis=1)

    return result[["cellosaurus_id", "context_score", "disease", "lineage"]]


if __name__ == "__main__":
    print("Scorer self-test (EGFR)...")
    hpa_to_cvcl, ach_to_cvcl, gsm_to_cvcl = load_mappings()

    rna = score_rna_expression("EGFR", hpa_to_cvcl, gsm_to_cvcl)
    print(f"RNA: {len(rna)} cell lines | "
          f"GEO bonus: {(rna['geo_confirmation'] > 0).sum()} | "
          f"GEO penalty: {(rna['geo_confirmation'] < 0).sum()} | "
          f"missing: {rna['missing_data_flag'].sum()}")
    print(rna.sort_values("rna_score", ascending=False).head(5).to_string(index=False))

    prot = score_protein_expression("EGFR", ach_to_cvcl)
    print(f"\nProtein: {len(prot)} cell lines")
    print(prot.sort_values("protein_score", ascending=False).head(5).to_string(index=False))

    crispr = score_crispr_dependency("EGFR")
    print(f"\nCRISPR dependency: {len(crispr)} cell lines")
    print(crispr.sort_values("dependency_score", ascending=False).head(5).to_string(index=False))
