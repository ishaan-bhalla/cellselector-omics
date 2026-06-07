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

# ---- Source 2: HPA (presence + name) ----
print("Loading HPA...")
hpa = pd.read_csv("data/11_hpa_rna_celline_description.tsv", sep="\t", low_memory=False)
hpa_names = hpa[["Cellosaurus ID","Cell line"]].dropna(subset=["Cellosaurus ID"])
hpa_names = hpa_names.rename(columns={"Cellosaurus ID":"cellosaurus_id","Cell line":"hpa_name"})
hpa_names = hpa_names.drop_duplicates("cellosaurus_id")
table["in_hpa"] = table["cellosaurus_id"].isin(set(hpa_names["cellosaurus_id"]))
table = table.merge(hpa_names, on="cellosaurus_id", how="left")

# ---- Source 3: GEO (presence + name) ----
print("Loading GEO...")
geo = pd.read_csv("data/10_GEOInfo.txt", sep="\t", low_memory=False)
geo_names = geo[["Cellosaurus_ID","cell_line"]].dropna(subset=["Cellosaurus_ID"])
geo_names = geo_names.rename(columns={"Cellosaurus_ID":"cellosaurus_id","cell_line":"geo_name"})
geo_names = geo_names.drop_duplicates("cellosaurus_id")
table["in_geo"] = table["cellosaurus_id"].isin(set(geo_names["cellosaurus_id"]))
table = table.merge(geo_names, on="cellosaurus_id", how="left")

# ---- Evidence count ----
table["evidence_count"] = table[["in_depmap","in_hpa","in_geo"]].sum(axis=1)

# ---- Official name from Cellosaurus ----
print("Loading Cellosaurus...")
cello = pd.read_csv("data/7_cellosaurus.csv", low_memory=False)
cs = cello[["Accession (CVCL_xxxx)","Identifier (cell line name)","Synonyms"]]
cs = cs.rename(columns={
    "Accession (CVCL_xxxx)":"cellosaurus_id",
    "Identifier (cell line name)":"official_name",
    "Synonyms":"synonyms",
})
table = table.merge(cs, on="cellosaurus_id", how="left")

# ---- Split matched vs unmatched ----
matched = table[table["cellosaurus_id"].notna()].copy()
unmatched = table[table["cellosaurus_id"].isna()].copy()

print("\nMatched:", len(matched), " Unmatched:", len(unmatched))

# ---- Save ----
matched.to_parquet("outputs/cell_line_lookup.parquet")
unmatched.to_csv("outputs/unmatched_cells.csv", index=False)
print("Saved lookup table and unmatched list to outputs/")

# ---- Show all names side by side for cells in all 3 sources ----
print("\nSame cell, every name it goes by:")
demo = matched[matched["evidence_count"]==3][["official_name","depmap_name","hpa_name","geo_name"]].head(6)
print(demo.to_string())

# ---- File 8: what data types exist per cell (RNA / WES / WGS) ----
print("Loading OmicsProfiles (file 8)...")
prof = pd.read_csv("data/8_DepMap_OmicsProfiles.csv", low_memory=False)
prof["has"] = True
datatypes = prof.pivot_table(index="ModelID", columns="Datatype", values="has", aggfunc="any", fill_value=False)
datatypes = datatypes.reset_index().rename(columns={
    "ModelID":"DepMap_ID",
    "rna":"has_rna",
    "wes":"has_wes",
    "wgs":"has_wgs",
})

# Merge this into the matched table
matched = matched.merge(datatypes, on="DepMap_ID", how="left")

# Count how many data types each cell has
matched["datatype_count"] = matched[["has_rna","has_wes","has_wgs"]].sum(axis=1)

# Save the updated table
matched.to_parquet("outputs/cell_line_lookup.parquet")
print("Added data-type info. Updated table saved.")

print("\nData types per cell:")
print(matched["datatype_count"].value_counts().sort_index().to_string())