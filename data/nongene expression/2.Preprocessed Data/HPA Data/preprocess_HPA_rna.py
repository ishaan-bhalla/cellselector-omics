

import pandas as pd
import os

INPUT_CELLINE  = "rna_celline.tsv"
INPUT_CANCER   = "rna_cell_line_cancer.tsv"
OUTPUT_CELLINE = "HPA_rna_wide.tsv"
OUTPUT_CANCER  = "HPA_rna_cancer_wide.tsv"
VALUE_COL      = "nTPM"   


def preprocess_celline(input_path, output_path, value_col):
    print(f"\n[1/4] Reading {input_path} ...")
    df = pd.read_csv(
        input_path,
        sep="\t",
        dtype={"TPM": "float32", "pTPM": "float32", "nTPM": "float32"},
    )
    print(f"      Rows: {len(df):,}  |  Genes: {df['Gene'].nunique():,}  |  Cell lines: {df['Cell line'].nunique():,}")

    print(f"\n[2/4] Pivoting to wide format using '{value_col}' ...")
    wide = df.pivot_table(
        index=["Gene", "Gene name"],
        columns="Cell line",
        values=value_col,
        aggfunc="first",
    ).reset_index()
    print(f"      Wide shape: {wide.shape[0]:,} genes x {wide.shape[1]:,} columns")

    print(f"\n[3/4] Saving to {output_path} ...")
    wide.to_csv(output_path, sep="\t", index=False)
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"      Saved ({size_mb:.1f} MB)")
    return wide


def preprocess_cancer(input_path, output_path, value_col):
    print(f"\n[4/4] Processing cancer-group file: {input_path} ...")
    df = pd.read_csv(
        input_path,
        sep="\t",
        dtype={"TPM": "float32", "pTPM": "float32", "nTPM": "float32"},
    )
    wide = df.pivot_table(
        index=["Gene", "Gene name"],
        columns="Cancer",
        values=value_col,
        aggfunc="first",
    ).reset_index()
    wide.to_csv(output_path, sep="\t", index=False)
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"      Saved {output_path} ({size_mb:.1f} MB)  |  Shape: {wide.shape}")
    return wide


if __name__ == "__main__":
    print("=" * 55)
    print("  HPA RNA Preprocessing")
    print("=" * 55)

    # Check inputs exist
    for path in [INPUT_CELLINE, INPUT_CANCER]:
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Input file not found: {path}\n"
                "Make sure the TSV files are in the same folder as this script."
            )

    celline_wide = preprocess_celline(INPUT_CELLINE, OUTPUT_CELLINE, VALUE_COL)
    cancer_wide  = preprocess_cancer(INPUT_CANCER,  OUTPUT_CANCER,  VALUE_COL)

    print("\n" + "=" * 55)
    print("  Done! Output files:")
    print(f"    {OUTPUT_CELLINE}")
    print(f"    {OUTPUT_CANCER}")
    print("=" * 55)
