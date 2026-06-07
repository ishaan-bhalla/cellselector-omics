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

# ---- Load Cellosaurus and build the synonym phone book ----
print("Loading Cellosaurus and building synonym index...")
cello = pd.read_csv("data/7_cellosaurus.csv", low_memory=False)

def clean(name):
    if pd.isna(name):
        return None
    return str(name).upper().replace(" ","").replace("-","").replace(".","").replace("_","")

syn_map = {}
for _, row in cello.iterrows():
    cvcl = row["Accession (CVCL_xxxx)"]
    official = clean(row["Identifier (cell line name)"])
    if official:
        syn_map.setdefault(official, cvcl)
    syns = row["Synonyms"]
    if pd.notna(syns):
        for s in str(syns).split(";"):
            c = clean(s)
            if c:
                syn_map.setdefault(c, cvcl)

# ---- Tier 2: rescue cells with no code, using synonym matching ----
table["match_type"] = None
rescued = 0
for i, row in table.iterrows():
    if pd.isna(row["cellosaurus_id"]):
        key = clean(row["depmap_name"])
        if key in syn_map:
            table.at[i,"cellosaurus_id"] = syn_map[key]
            table.at[i,"match_type"] = "synonym"
            rescued += 1
    else:
        table.at[i,"match_type"] = "direct"
print("Rescued", rescued, "cells via synonym matching.")

# ---- Source 2: HPA (presence + name) ----
print("Loading HPA...")
hpa = pd.read_csv("data/11_hpa_rna_celline_description.tsv", sep="\t", low_memory=False)
hpa_names = hpa[["Cellosaurus ID","Cell line"]].dropna(subset=["Cellosaurus ID"])
hpa_names = hpa_names.rename(columns={"Cellosaurus ID":"cellosaurus_id","Cell line":"hpa_name"}).drop_duplicates("cellosaurus_id")
table["in_hpa"] = table["cellosaurus_id"].isin(set(hpa_names["cellosaurus_id"]))
table = table.merge(hpa_names, on="cellosaurus_id", how="left")

# ---- Source 3: GEO (presence + name) ----
print("Loading GEO...")
geo = pd.read_csv("data/10_GEOInfo.txt", sep="\t", low_memory=False)
geo_names = geo[["Cellosaurus_ID","cell_line"]].dropna(subset=["Cellosaurus_ID"])
geo_names = geo_names.rename(columns={"Cellosaurus_ID":"cellosaurus_id","cell_line":"geo_name"}).drop_duplicates("cellosaurus_id")
table["in_geo"] = table["cellosaurus_id"].isin(set(geo_names["cellosaurus_id"]))
table = table.merge(geo_names, on="cellosaurus_id", how="left")

# ---- Evidence count ----
table["evidence_count"] = table[["in_depmap","in_hpa","in_geo"]].sum(axis=1)

# ---- Official names + synonyms ----
cs = cello[["Accession (CVCL_xxxx)","Identifier (cell line name)","Synonyms"]]
cs = cs.rename(columns={
    "Accession (CVCL_xxxx)":"cellosaurus_id",
    "Identifier (cell line name)":"official_name",
    "Synonyms":"synonyms",
})
table = table.merge(cs, on="cellosaurus_id", how="left")

# ---- File 8: what data types exist (RNA / WES / WGS) ----
print("Loading OmicsProfiles (file 8)...")
prof = pd.read_csv("data/8_DepMap_OmicsProfiles.csv", low_memory=False)
prof["has"] = True
datatypes = prof.pivot_table(index="ModelID", columns="Datatype", values="has", aggfunc="any", fill_value=False)
datatypes = datatypes.reset_index().rename(columns={
    "ModelID":"DepMap_ID","rna":"has_rna","wes":"has_wes","wgs":"has_wgs",
})
table = table.merge(datatypes, on="DepMap_ID", how="left")
table["datatype_count"] = table[["has_rna","has_wes","has_wgs"]].sum(axis=1)

# ---- Split matched vs unmatched ----
matched = table[table["cellosaurus_id"].notna()].copy()
unmatched = table[table["cellosaurus_id"].isna()].copy()

# ---- Save ----
matched.to_parquet("outputs/cell_line_lookup.parquet")
unmatched.to_csv("outputs/unmatched_cells.csv", index=False)

print("\nMatched:", len(matched), " Unmatched:", len(unmatched))
print("\nMatch type breakdown:")
print(matched["match_type"].value_counts().to_string())
print("\nSaved final lookup table and unmatched list to outputs/")