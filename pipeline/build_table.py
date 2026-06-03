import pandas as pd

# ---- Source 1: DepMap ----
print("Loading DepMap...")
samp = pd.read_csv("data/9_DepMap_sample_info.csv", low_memory=False)
table = samp[["RRID","DepMap_ID","stripped_cell_line_name","primary_disease","lineage"]].copy()
table = table.rename(columns={
    "RRID":"cellosaurus_id",
    "stripped_cell_line_name":"depmap_name",
    "primary_disease":"disease",
})
table["in_depmap"] = True

# ---- Source 2: HPA ----
print("Loading HPA...")
hpa = pd.read_csv("data/11_hpa_rna_celline_description.tsv", sep="\t", low_memory=False)
table["in_hpa"] = table["cellosaurus_id"].isin(set(hpa["Cellosaurus ID"].dropna()))

# ---- Source 3: GEO ----
print("Loading GEO...")
geo = pd.read_csv("data/10_GEOInfo.txt", sep="\t", low_memory=False)
table["in_geo"] = table["cellosaurus_id"].isin(set(geo["Cellosaurus_ID"].dropna()))

# ---- Evidence count ----
table["evidence_count"] = table[["in_depmap","in_hpa","in_geo"]].sum(axis=1)

# ---- Add official names and synonyms from Cellosaurus ----
print("Loading Cellosaurus for official names...")
cello = pd.read_csv("data/7_cellosaurus.csv", low_memory=False)
cello_small = cello[["Accession (CVCL_xxxx)","Identifier (cell line name)","Synonyms"]].rename(columns={
    "Accession (CVCL_xxxx)":"cellosaurus_id",
    "Identifier (cell line name)":"official_name",
    "Synonyms":"synonyms",
})
table = table.merge(cello_small, on="cellosaurus_id", how="left")

# ---- Split matched vs unmatched (honest tracking) ----
matched = table[table["cellosaurus_id"].notna()].copy()
unmatched = table[table["cellosaurus_id"].isna()].copy()

print("\nMatched cell lines:", len(matched))
print("Unmatched cell lines:", len(unmatched))

# ---- Save both ----
matched.to_parquet("outputs/cell_line_lookup.parquet")
unmatched.to_csv("outputs/unmatched_cells.csv", index=False)
print("\nSaved matched table to outputs/cell_line_lookup.parquet")
print("Saved unmatched list to outputs/unmatched_cells.csv")

print("\nSample of the matched table:")
print(matched[["cellosaurus_id","official_name","depmap_name","disease","evidence_count"]].head(6).to_string())