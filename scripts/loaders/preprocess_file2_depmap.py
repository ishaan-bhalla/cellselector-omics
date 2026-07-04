import math
import re
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config import FILES, PARQUET_DIR, setup_dirs

OUTPUT_NAME = "gene_expr_depmap_preprocessed.parquet"
COL_CHUNK   = 2000   # gene columns loaded per CSV pass

STANDARD_COLS = [
    "original_id",
    "original_id_type",
    "gene_id",
    "gene_symbol",
    "expression_value",
    "source",
    "units",
    "date_processed",
]

# Pattern A: "TSPAN6 (ENSG00000000003)"  → symbol + ENSG
# Pattern B: "ENSG00000285776"            → bare ENSG, no symbol
_SYMBOL_ENSG_RE = re.compile(r"^(.+?)\s+\((ENSG\d+)\)$")

# NOTE: PR- row IDs are DepMap OmicsProfile IDs (one sequencing run per profile).
# A single cell line (ACH-) can have multiple PR- rows.
# Mapping PR- → ACH- → cellosaurus_id requires data/8_DepMap_OmicsProfiles.csv
# and is handled at merge time, not here.


def parse_gene_columns(col_names: list[str]) -> tuple[dict, dict, dict, list]:
    """
    Returns:
      gene_id_map : raw_col → gene_id (ENSG where available, else raw name)
      symbol_map  : raw_col → gene_symbol (str or None)
      counts      : {'A': n, 'B': n, 'C': n}
      failed      : list of columns matching Pattern C
    """
    gene_id_map: dict[str, str]        = {}
    symbol_map:  dict[str, str | None] = {}
    counts = {"A": 0, "B": 0, "C": 0}
    failed: list[str] = []

    for col in col_names:
        m = _SYMBOL_ENSG_RE.match(col)
        if m:
            gene_id_map[col] = m.group(2)   # ENSG ID
            symbol_map[col]  = m.group(1)   # HGNC symbol
            counts["A"] += 1
        elif col.startswith("ENSG"):
            gene_id_map[col] = col
            symbol_map[col]  = None
            counts["B"] += 1
        else:
            gene_id_map[col] = col
            symbol_map[col]  = None
            counts["C"] += 1
            failed.append(col)

    return gene_id_map, symbol_map, counts, failed


def preprocess_file2() -> pd.DataFrame:
    t0 = time.perf_counter()
    setup_dirs()

    src_path = FILES["depmap"]
    out_path = PARQUET_DIR / OUTPUT_NAME
    today    = date.today().strftime("%Y-%m-%d")

    size_gb = src_path.stat().st_size / 1_073_741_824
    print(f"\nSource  : {src_path.name}  ({size_gb:.2f} GB)")

    # ── Step 1: read column names only ────────────────────────────────────────
    print("Reading column headers …")
    all_cols  = pd.read_csv(src_path, nrows=0).columns.tolist()
    id_col    = all_cols[0]          # "Unnamed: 0"  → PR- profile IDs
    gene_cols = all_cols[1:]         # 53,961 gene columns
    n_genes   = len(gene_cols)
    n_chunks  = math.ceil(n_genes / COL_CHUNK)

    print(f"ID column   : '{id_col}'")
    print(f"Gene columns: {n_genes:,}")
    print(f"Col chunks  : {n_chunks}  ({COL_CHUNK} gene cols each)")

    # ── Step 2: pre-parse all column names in one pass (pure string ops) ──────
    gene_id_map, symbol_map, counts, failed_cols = parse_gene_columns(gene_cols)

    print(f"\nColumn name parsing:")
    print(f"  Pattern A  SYMBOL (ENSG…) : {counts['A']:,}")
    print(f"  Pattern B  bare ENSG      : {counts['B']:,}")
    print(f"  Pattern C  other (failed) : {counts['C']:,}")
    if failed_cols:
        for c in failed_cols:
            print(f"    - {c!r}")

    # ── Step 3: column-chunked CSV load → melt → stream to Parquet ───────────
    # Each pass loads 1,495 rows × ≤2,000 gene cols (~23 MB as float32).
    # Melt output per chunk: up to 1,495 × 2,000 = 2,990,000 rows → manageable.
    print(f"\nColumn-chunked processing ({n_chunks} passes over the CSV) …")

    writer        = None
    rows_out      = 0
    unique_pr_ids = None

    for chunk_idx, start in enumerate(range(0, n_genes, COL_CHUNK), 1):
        t_chunk        = time.perf_counter()
        chunk_cols     = gene_cols[start:start + COL_CHUNK]
        dtype_map      = {c: "float32" for c in chunk_cols}

        df = pd.read_csv(src_path, usecols=[id_col] + chunk_cols, dtype=dtype_map)

        if unique_pr_ids is None:
            unique_pr_ids = df[id_col].tolist()

        df = df.rename(columns={id_col: "original_id"})

        long = df.melt(
            id_vars=["original_id"],
            var_name="_raw_col",
            value_name="expression_value",
        )

        long["gene_id"]    = long["_raw_col"].map(gene_id_map)
        long["gene_symbol"] = long["_raw_col"].map(symbol_map)
        long = long.drop(columns="_raw_col")

        n = len(long)
        long["original_id_type"] = pd.Categorical(["PR"] * n,          categories=["PR"])
        long["source"]           = pd.Categorical(["DepMap_TPM"] * n,  categories=["DepMap_TPM"])
        long["units"]            = pd.Categorical(["TPM_log1p"] * n,    categories=["TPM_log1p"])
        long["date_processed"]   = pd.Categorical([today] * n,          categories=[today])

        long = long[STANDARD_COLS]
        rows_out += n

        table = pa.Table.from_pandas(long, preserve_index=False)
        if writer is None:
            writer = pq.ParquetWriter(out_path, table.schema, compression="snappy")
        writer.write_table(table)

        chunk_t = time.perf_counter() - t_chunk
        total_t = time.perf_counter() - t0
        print(
            f"  chunk {chunk_idx:>3}/{n_chunks}"
            f"  cols {start + 1:>6}–{start + len(chunk_cols):<6}"
            f"  |  {n:>9,} rows"
            f"  |  {chunk_t:>5.1f}s/chunk"
            f"  |  {total_t:>6.1f}s total"
        )

    if writer:
        writer.close()

    elapsed    = time.perf_counter() - t0
    parquet_mb = out_path.stat().st_size / 1_048_576
    expected   = len(unique_pr_ids) * n_genes

    sample = pd.read_parquet(out_path).head(5)

    print(f"\n{'─'*66}")
    print(f"Total gene columns       : {n_genes:,}")
    print(f"Pattern A (SYMBOL+ENSG)  : {counts['A']:,}")
    print(f"Pattern B (bare ENSG)    : {counts['B']:,}")
    print(f"Pattern C (failed)       : {counts['C']:,}")
    print(f"Column chunks processed  : {n_chunks}")
    print(f"Unique PR- profiles      : {len(unique_pr_ids):,}")
    print(f"Expected row count       : {expected:,}  (1,495 × {n_genes:,})")
    print(f"Actual row count         : {rows_out:,}")
    print(f"Final shape              : {rows_out:,} rows × 8 columns")
    print(f"Parquet size on disk     : {parquet_mb:.1f} MB")
    print(f"Time taken               : {elapsed:.1f}s")
    print(f"\nColumn order: {STANDARD_COLS}")
    print(f"\nSample output (5 rows):")
    print(sample.to_string(index=False))
    print(f"\nSaved → {out_path}")

    return sample


if __name__ == "__main__":
    df = preprocess_file2()
