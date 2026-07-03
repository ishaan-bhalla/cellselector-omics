import pandas as pd

# ============================================================
# MERGE SCRIPT
# Spine = nomenclature lookup table (shared cell line IDs).
# Each member's cleaned data is mapped onto it by cellosaurus_id.
# ============================================================

# ---- Spine: the nomenclature lookup ----
print("Loading spine (nomenclature lookup)...")
master = pd.read_parquet("outputs/cell_line_lookup.parquet")
master = master[["cellosaurus_id", "DepMap_ID", "official_name", "evidence_count"]].copy()

# ---- ID translation maps (from DepMap sample info) ----
samp = pd.read_csv("data/9_DepMap_sample_info.csv", low_memory=False)
dep_to_cvcl = dict(zip(samp["DepMap_ID"], samp["RRID"]))
ccle_to_cvcl = dict(zip(samp["CCLE_Name"], samp["RRID"]))

# ============================================================
# MEMBER 4 - non gene expression
# ============================================================
print("Merging Member 4 (non gene expression)...")

# File 1: genome signatures (keyed by DepMap ModelID) - attach features
sig = pd.read_csv("data/member4/OmicsGlobalSignatures_clean.tsv", sep="\t", low_memory=False)
sig["cellosaurus_id"] = sig["ModelID"].map(dep_to_cvcl)
sig = sig.dropna(subset=["cellosaurus_id"]).drop(columns=["ModelID"]).drop_duplicates("cellosaurus_id")
master = master.merge(sig, on="cellosaurus_id", how="left")

# File 2: metabolomics (cell lines are columns = DepMap IDs) - add coverage flag
met = pd.read_csv("data/member4/CCLE_metabolomics_wide.tsv", sep="\t", nrows=1, low_memory=False)
met_cvcls = {dep_to_cvcl.get(c) for c in met.columns if c.startswith("ACH-")}
master["has_metabolomics"] = master["cellosaurus_id"].isin(met_cvcls)

# File 3: miRNA (cell lines are columns = CCLE names) - add coverage flag
mir = pd.read_csv("data/member4/CCLE_miRNA_wide.tsv", sep="\t", nrows=1, low_memory=False)
mir_cvcls = {ccle_to_cvcl.get(c) for c in mir.columns if c != "miRNA"}
master["has_mirna"] = master["cellosaurus_id"].isin(mir_cvcls)

# ============================================================
# MEMBER 2 - gene expression   (add when their data arrives)
# ============================================================

# ============================================================
# MEMBER 3 - gene properties   (add when their data arrives)
# ============================================================

# ---- Save the merged master table ----
master.to_parquet("outputs/master_merged.parquet")

print("\nMerged master table:", master.shape[0], "cells,", master.shape[1], "columns")
print("Cells with signature features:", master["MSIScore"].notna().sum())
print("Cells with metabolomics:", master["has_metabolomics"].sum())
print("Cells with miRNA:", master["has_mirna"].sum())
print("\nSaved to outputs/master_merged.parquet")