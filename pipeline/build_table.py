import pandas as pd

# ---- Source 1: DepMap (the starting point) ----
print("Loading DepMap...")
samp = pd.read_csv("data/9_DepMap_sample_info.csv", low_memory=False)
table = samp[["RRID","DepMap_ID","stripped_cell_line_name","primary_disease","lineage"]].copy()
table = table.rename(columns={
    "RRID":"cellosaurus_id",
    "stripped_cell_line_name":"name",
    "primary_disease":"disease",
})
table["in_depmap"] = True

# ---- Source 2: HPA ----
print("Loading HPA...")
hpa = pd.read_csv("data/11_hpa_rna_celline_description.tsv", sep="\t", low_memory=False)
hpa_ids = set(hpa["Cellosaurus ID"].dropna())
table["in_hpa"] = table["cellosaurus_id"].isin(hpa_ids)

# ---- Source 3: GEO ----
print("Loading GEO...")
geo = pd.read_csv("data/10_GEOInfo.txt", sep="\t", low_memory=False)
geo_ids = set(geo["Cellosaurus_ID"].dropna())
table["in_geo"] = table["cellosaurus_id"].isin(geo_ids)

# ---- Evidence count: how many sources each cell appears in ----
table["evidence_count"] = table[["in_depmap","in_hpa","in_geo"]].sum(axis=1)

# ---- Show the result ----
print("\nTranslation table with evidence count:")
print(table[["cellosaurus_id","name","disease","in_depmap","in_hpa","in_geo","evidence_count"]].head(8).to_string())

print("\nHow many cell lines have each evidence count:")
print(table["evidence_count"].value_counts().sort_index().to_string())
# Save the table so the team can use it
table.to_parquet("outputs/cell_line_lookup.parquet")
print("\nSaved to outputs/cell_line_lookup.parquet")