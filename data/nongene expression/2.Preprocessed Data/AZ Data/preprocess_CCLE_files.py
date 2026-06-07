

import pandas as pd
import os
import sys


INPUT_METABOLOMICS   = "12_CCLE_metabolomics_20190502.csv"
INPUT_MIRNA          = "13_CCLE_miRNA_20181103.gct"
INPUT_OMICS          = "14_OmicsGlobalSignatures.csv"

OUTPUT_METABOLOMICS  = "CCLE_metabolomics_wide.tsv"
OUTPUT_MIRNA         = "CCLE_miRNA_wide.tsv"
OUTPUT_OMICS         = "OmicsGlobalSignatures_clean.tsv"



def check_inputs():
    """Make sure all input files exist before starting."""
    missing = [f for f in [INPUT_METABOLOMICS, INPUT_MIRNA, INPUT_OMICS]
               if not os.path.exists(f)]
    if missing:
        print("ERROR: Missing input files:")
        for f in missing:
            print(f"  - {f}")
        print("\nMake sure all input files are in the same folder as this script.")
        sys.exit(1)


def file_size_kb(path):
    return os.path.getsize(path) / 1024


#File 1 CCLE METABOLOMICS
def process_metabolomics():
    print("\n[1/3] CCLE Metabolomics")
    print(f"      Reading: {INPUT_METABOLOMICS}")

    df = pd.read_csv(INPUT_METABOLOMICS)

    # DepMapID
    df = df.drop(columns=["CCLE_ID"])
    df = df.set_index("DepMap_ID")

    # Transpose so rows = metabolites, columns = cell lines
    # This matches the format of HPA_rna_wide and DepMap matrices
    df_wide = df.T
    df_wide.index.name = "Metabolite"
    df_wide.columns.name = None

    df_wide.to_csv(OUTPUT_METABOLOMICS, sep="\t")

    print(f"      Shape  : {df_wide.shape[0]} metabolites x {df_wide.shape[1]} cell lines")
    print(f"      Missing: {df_wide.isnull().sum().sum()} values")
    print(f"      Saved  : {OUTPUT_METABOLOMICS} ({file_size_kb(OUTPUT_METABOLOMICS):.0f} KB)")
    print(f"      ID type: DepMap ACH IDs (columns)")
    return df_wide


# FILE 2 CCLE miRNA 
def process_mirna():
    """
    GCT format has 2 header rows to skip:
      Row 1: #1.2
      Row 2: [num_rows]  [num_cols]
      Row 3+: Name | Description | cell_line_1 | cell_line_2 ...
    """
    print("\n[2/3] CCLE miRNA Expression")
    print(f"      Reading: {INPUT_MIRNA}")

    df = pd.read_csv(INPUT_MIRNA, sep="\t", skiprows=2)

    # Fix Name
    df = df.drop(columns=["Name"])
    df = df.set_index("Description")
    df.index.name = "miRNA"
    df.columns.name = None

    # Numerize
    df = df.apply(pd.to_numeric, errors="coerce")

    df.to_csv(OUTPUT_MIRNA, sep="\t")

    print(f"      Shape  : {df.shape[0]} miRNAs x {df.shape[1]} cell lines")
    print(f"      Missing: {df.isnull().sum().sum()} values")
    print(f"      Saved  : {OUTPUT_MIRNA} ({file_size_kb(OUTPUT_MIRNA):.0f} KB)")
    print(f"      ID type: CCLE format (e.g. DMS53_LUNG) — columns")
    print(f"      Note   : To merge with DepMap data, map CCLE_ID → DepMap_ID")
    return df


# FILE 3 OMICS GLOBAL SIGNATURES 
def process_omics():
    """
    Contains genomic signatures per cell line:
      MSIScore    - Microsatellite instability score
      LoHFraction - Loss of heterozygosity fraction
      WGD         - Whole genome doubling (0/1)
      CIN         - Chromosomal instability score
      Ploidy      - Estimated ploidy
      Aneuploidy  - Aneuploidy score
    """
    print("\n[3/3] OmicsGlobalSignatures")
    print(f"      Reading: {INPUT_OMICS}")

    df = pd.read_csv(INPUT_OMICS, index_col=0)

    # Keep only the default/canonical entry per cell line model
    # (some models have multiple sequencing entries)
    before = len(df)
    df = df[df["IsDefaultEntryForModel"] == "Yes"].copy()
    after = len(df)
    print(f"      Deduplication: {before} → {after} rows (kept default entry per model)")

    # Set ModelID (DepMap ACH ID) as row index — standard key
    df = df.set_index("ModelID")

    # Drop admin columns no longer needed
    df = df.drop(columns=["SequencingID", "ModelConditionID",
                           "IsDefaultEntryForModel", "IsDefaultEntryForMC"])

    # Report missingness (333 rows have no genomic metrics — this is expected)
    missing = df.isnull().sum()
    print(f"      Missing values per feature:")
    for col, n in missing.items():
        flag = "  ← expected for some models" if n > 0 else ""
        print(f"        {col}: {n}{flag}")

    df.to_csv(OUTPUT_OMICS, sep="\t")

    print(f"      Shape  : {df.shape[0]} cell lines x {df.shape[1]} features")
    print(f"      Saved  : {OUTPUT_OMICS} ({file_size_kb(OUTPUT_OMICS):.0f} KB)")
    print(f"      ID type: DepMap ACH IDs (index)")
    return df


# ── MAIN ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  CellLineFinder — CCLE/DepMap Preprocessing Pipeline")
    print("=" * 60)

    check_inputs()

    df_metabolomics = process_metabolomics()
    df_mirna        = process_mirna()
    df_omics        = process_omics()

    print("\n" + "=" * 60)
    print("  ALL DONE — Summary of outputs:")
    print(f"    {OUTPUT_METABOLOMICS:<35} {df_metabolomics.shape[0]} metabolites × {df_metabolomics.shape[1]} cell lines")
    print(f"    {OUTPUT_MIRNA:<35} {df_mirna.shape[0]} miRNAs × {df_mirna.shape[1]} cell lines")
    print(f"    {OUTPUT_OMICS:<35} {df_omics.shape[0]} cell lines × {df_omics.shape[1]} features")
    print()
    print("  ID KEY:")
    print("    Metabolomics & Omics → DepMap ACH IDs  (e.g. ACH-000001)")
    print("    miRNA               → CCLE IDs         (e.g. DMS53_LUNG)")
    print("    Use a DepMap sample_info file to map CCLE ↔ DepMap IDs")
    print("=" * 60)
