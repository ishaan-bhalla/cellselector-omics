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


def load_mappings() -> tuple[dict, dict, dict]:
    """Load all ID translation dicts.

    Returns: (hpa_to_cvcl, ach_to_cvcl, gsm_to_cvcl)
    """
    lkp = pd.read_parquet(CELL_LINE_LOOKUP, columns=["cellosaurus_id", "hpa_name"])
    hpa_to_cvcl = dict(zip(lkp["hpa_name"].dropna(), lkp["cellosaurus_id"].dropna()))

    samp = pd.read_csv(SAMPLE_INFO, usecols=["DepMap_ID", "RRID"], low_memory=False)
    ach_to_cvcl = {
        row.DepMap_ID: row.RRID
        for row in samp.itertuples()
        if pd.notna(row.RRID)
    }

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


def score_rna_expression(gene: str, hpa_to_cvcl: dict, gsm_to_cvcl: dict) -> pd.DataFrame:
    """Score RNA expression from HPA, DepMap, and GEO for a given gene.

    Columns: cellosaurus_id, rna_score, n_rna_sources,
             hpa_score, depmap_score, geo_score
    """
    _empty = pd.DataFrame(
        columns=["cellosaurus_id", "rna_score", "n_rna_sources",
                 "hpa_score", "depmap_score", "geo_score"]
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
                pd.DataFrame({"cellosaurus_id": cvcl[mask].values,
                               "hpa_score": _pct_rank(agg[mask])})
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

    # ── GEO: no threshold (units unknown) ────────────────────────────────────
    geo_raw = pd.read_parquet(
        PARQUET_DIR / "gene_expr_geo_preprocessed.parquet",
        filters=[("gene_symbol", "=", gene)],
        columns=["original_id", "expression_value"],
    )
    geo_df = pd.DataFrame(columns=["cellosaurus_id", "geo_score"])
    if len(geo_raw) > 0:
        geo_raw["cellosaurus_id"] = geo_raw["original_id"].map(gsm_to_cvcl)
        geo_raw = geo_raw.dropna(subset=["cellosaurus_id"])
        if len(geo_raw) > 0:
            agg = geo_raw.groupby("cellosaurus_id")["expression_value"].mean()
            geo_df = pd.DataFrame({
                "cellosaurus_id": agg.index,
                "geo_score": _pct_rank(agg),
            })

    # ── Weighted merge ────────────────────────────────────────────────────────
    all_cvcl = (
        set(hpa_df["cellosaurus_id"])
        | set(dep_df["cellosaurus_id"])
        | set(geo_df["cellosaurus_id"])
    )
    if not all_cvcl:
        return _empty

    result = (
        pd.DataFrame({"cellosaurus_id": list(all_cvcl)})
        .merge(hpa_df, on="cellosaurus_id", how="left")
        .merge(dep_df, on="cellosaurus_id", how="left")
        .merge(geo_df, on="cellosaurus_id", how="left")
    )

    _W = {"hpa_score": 0.4, "depmap_score": 0.4, "geo_score": 0.2}

    def _weighted(row):
        avail = {k: w for k, w in _W.items() if pd.notna(row[k])}
        if not avail:
            return np.nan, 0
        total = sum(avail.values())
        return sum(row[k] * w / total for k, w in avail.items()), len(avail)

    combined = result.apply(_weighted, axis=1)
    result["rna_score"] = [v[0] for v in combined]
    result["n_rna_sources"] = [v[1] for v in combined]

    return result[["cellosaurus_id", "rna_score", "n_rna_sources",
                   "hpa_score", "depmap_score", "geo_score"]]


def score_protein_expression(gene: str, ach_to_cvcl: dict) -> pd.DataFrame:
    """Score protein expression from CCLE MS proteomics for a given gene.

    Columns: cellosaurus_id, protein_score
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


def score_data_quality(
    cellosaurus_ids,
    rna_df: pd.DataFrame,
    protein_df: pd.DataFrame,
) -> pd.DataFrame:
    """Score data quality for each cell line.

    quality_score = 0.4*(n_sources/3) + 0.4*(1 - cross_source_std) + 0.2*completeness

    Columns: cellosaurus_id, quality_score, n_sources, cross_source_std, completeness
    """
    conf = pd.read_parquet(MASTER_CONFIDENCE, columns=["cellosaurus_id", "confidence"])

    rna_cols = ["cellosaurus_id", "n_rna_sources", "hpa_score", "depmap_score", "geo_score"]
    rna_subset = rna_df[[c for c in rna_cols if c in rna_df.columns]]

    result = (
        pd.DataFrame({"cellosaurus_id": list(cellosaurus_ids)})
        .merge(rna_subset, on="cellosaurus_id", how="left")
        .merge(conf, on="cellosaurus_id", how="left")
    )

    for col in ["n_rna_sources", "hpa_score", "depmap_score", "geo_score"]:
        if col not in result.columns:
            result[col] = np.nan

    source_cols = ["hpa_score", "depmap_score", "geo_score"]
    result["cross_source_std"] = result[source_cols].std(axis=1, skipna=True).fillna(0.0)
    result["n_sources"] = result["n_rna_sources"].fillna(0.0)
    result["completeness"] = result["confidence"].fillna(0.0)

    result["quality_score"] = (
        0.4 * (result["n_sources"] / 3.0)
        + 0.4 * (1.0 - result["cross_source_std"])
        + 0.2 * result["completeness"]
    )

    return result[["cellosaurus_id", "quality_score", "n_sources",
                   "cross_source_std", "completeness"]]


def score_context(
    cellosaurus_ids,
    disease_filter: str | None = None,
    lineage_filter: str | None = None,
) -> pd.DataFrame:
    """Score disease/lineage context match for each cell line.

    context_score = max(disease_match, lineage_match); 1.0 if filter matches, else 0.0

    Columns: cellosaurus_id, context_score, disease, lineage
    """
    lkp = pd.read_parquet(
        CELL_LINE_LOOKUP, columns=["cellosaurus_id", "disease", "lineage"]
    )
    result = pd.DataFrame({"cellosaurus_id": list(cellosaurus_ids)}).merge(
        lkp, on="cellosaurus_id", how="left"
    )

    result["disease_match"] = (
        result["disease"].fillna("").str.lower()
        .str.contains(disease_filter.lower(), regex=False)
        .astype(float)
    ) if disease_filter else 0.0

    result["lineage_match"] = (
        result["lineage"].fillna("").str.lower()
        .str.contains(lineage_filter.lower(), regex=False)
        .astype(float)
    ) if lineage_filter else 0.0

    result["context_score"] = result[["disease_match", "lineage_match"]].max(axis=1)

    return result[["cellosaurus_id", "context_score", "disease", "lineage"]]


if __name__ == "__main__":
    print("Testing scorer with EGFR...")
    hpa_to_cvcl, ach_to_cvcl, gsm_to_cvcl = load_mappings()
    print(f"  HPA mappings: {len(hpa_to_cvcl):,}")
    print(f"  ACH mappings: {len(ach_to_cvcl):,}")
    print(f"  GSM mappings: {len(gsm_to_cvcl):,}")

    rna = score_rna_expression("EGFR", hpa_to_cvcl, gsm_to_cvcl)
    print(f"\nRNA scores: {len(rna)} cell lines")
    print(rna.sort_values("rna_score", ascending=False).head(5).to_string(index=False))

    prot = score_protein_expression("EGFR", ach_to_cvcl)
    print(f"\nProtein scores: {len(prot)} cell lines")
    print(prot.sort_values("protein_score", ascending=False).head(5).to_string(index=False))
