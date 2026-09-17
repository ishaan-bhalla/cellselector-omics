import json
import sys
import time
from pathlib import Path

import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config import OUTPUTS_DIR, PARQUET_DIR
from models.classical.scorer import load_mappings

# ─────────────────────────────────────────────────────────────────────────────
# Precompute gene -> total_cell_lines_with_data, matching
# api._count_cell_lines_with_data's exact original (now-replaced) live
# definition: len(set(rna_df.cellosaurus_id) | set(protein_df.cellosaurus_id))
# where rna's set is HPA (nTPM > 1.0) UNION DepMap (TPM_log1p > 0.5) — GEO
# is deliberately excluded, since score_rna_expression's own all_cvcl never
# includes it either (it only contributes a confirmation bonus, applied
# after the cell-line set is already fixed — see scorer.score_rna_expression).
#
# WHY THIS EXISTS (see the /genes/search performance investigation):
# score_rna_expression/score_protein_expression's per-call disk reads
# (pd.read_parquet(..., filters=...)) took ~10-13s per gene lookup — the
# obvious fix looked like "load these files into memory once at startup",
# same lifespan-hook pattern as master_merged. That was tried and directly
# measured to be UNSAFE: these files are 65-80 MILLION rows each (the
# ~750MB figure used to judge it "feasible" was the on-disk COMPRESSED
# size, not a proxy for in-memory footprint) — loading even the smallest
# of the four OOM-killed a 3GB-capped isolated test container, and doing
# this for real (in the live server process) is what took the production
# VM itself down.
#
# This script instead does the ONE necessary full scan of these files
# OFFLINE, streamed via pyarrow's iter_batches (bounded batch size) so the
# full ~150M+ rows across HPA/DepMap/proteomics are never materialized in
# memory at once, and writes a tiny gene->int JSON (~750KB for ~48K genes)
# that api/main.py's lifespan hook loads directly — trivially safe. Regenerate
# this whenever the underlying expression parquet files change.
# ─────────────────────────────────────────────────────────────────────────────

BATCH_SIZE = 500_000

_cvcl_index: dict[str, int] = {}


def _cvcl_id(cvcl: str) -> int:
    """Intern a cellosaurus_id string to a small int — a set of ints is far
    more compact than a set of repeated ~10-char strings at this scale
    (the accumulator otherwise holds up to ~50K genes x however many cell
    lines qualify for each)."""
    idx = _cvcl_index.get(cvcl)
    if idx is None:
        idx = len(_cvcl_index)
        _cvcl_index[cvcl] = idx
    return idx


def _scan_hpa(hpa_to_cvcl: dict, acc: dict[str, set]) -> None:
    pf = pq.ParquetFile(PARQUET_DIR / "gene_expr_hpa_preprocessed.parquet")
    n_batches = 0
    for batch in pf.iter_batches(
        batch_size=BATCH_SIZE, columns=["gene_symbol", "units", "original_id", "expression_value"]
    ):
        df = batch.to_pandas()
        df = df[(df["units"] == "nTPM") & (df["expression_value"] > 1.0)]
        if len(df) > 0:
            df["cvcl"] = df["original_id"].map(hpa_to_cvcl)
            df = df.dropna(subset=["cvcl"])
            for gene, cvcl in zip(df["gene_symbol"].values, df["cvcl"].values):
                acc.setdefault(gene, set()).add(_cvcl_id(cvcl))
        n_batches += 1
        if n_batches % 20 == 0:
            print(f"  [hpa] batch {n_batches}, {len(acc)} genes so far, "
                  f"{len(_cvcl_index)} distinct cell lines interned", flush=True)


def _scan_depmap(acc: dict[str, set]) -> None:
    pf = pq.ParquetFile(PARQUET_DIR / "gene_expr_depmap_preprocessed.parquet")
    n_batches = 0
    for batch in pf.iter_batches(
        batch_size=BATCH_SIZE, columns=["gene_symbol", "cellosaurus_id", "expression_value"]
    ):
        df = batch.to_pandas()
        df = df.dropna(subset=["cellosaurus_id"])
        df = df[df["expression_value"] > 0.5]
        if len(df) > 0:
            for gene, cvcl in zip(df["gene_symbol"].values, df["cellosaurus_id"].values):
                acc.setdefault(gene, set()).add(_cvcl_id(cvcl))
        n_batches += 1
        if n_batches % 20 == 0:
            print(f"  [depmap] batch {n_batches}, {len(acc)} genes so far", flush=True)


def _scan_proteomics(ach_to_cvcl: dict, acc: dict[str, set]) -> None:
    pf = pq.ParquetFile(PARQUET_DIR / "gene_expr_ccle_proteomics_preprocessed.parquet")
    n_batches = 0
    for batch in pf.iter_batches(
        batch_size=BATCH_SIZE, columns=["gene_symbol", "original_id", "expression_value"]
    ):
        df = batch.to_pandas()
        df["cvcl"] = df["original_id"].map(ach_to_cvcl)
        df = df.dropna(subset=["cvcl"])
        if len(df) > 0:
            for gene, cvcl in zip(df["gene_symbol"].values, df["cvcl"].values):
                acc.setdefault(gene, set()).add(_cvcl_id(cvcl))
        n_batches += 1
        if n_batches % 5 == 0:
            print(f"  [proteomics] batch {n_batches}, {len(acc)} genes so far", flush=True)


def precompute_gene_cellline_counts() -> dict[str, int]:
    t0 = time.time()
    hpa_to_cvcl, ach_to_cvcl, gsm_to_cvcl = load_mappings()

    rna_acc: dict[str, set] = {}
    print("Scanning HPA...", flush=True)
    _scan_hpa(hpa_to_cvcl, rna_acc)
    print(f"HPA done, {len(rna_acc)} genes, {len(_cvcl_index)} distinct cell lines so far", flush=True)

    print("Scanning DepMap...", flush=True)
    _scan_depmap(rna_acc)  # merges into the SAME rna_acc — union, matching all_cvcl = hpa | depmap
    print(f"DepMap done, {len(rna_acc)} genes total", flush=True)

    protein_acc: dict[str, set] = {}
    print("Scanning proteomics...", flush=True)
    _scan_proteomics(ach_to_cvcl, protein_acc)
    print(f"Proteomics done, {len(protein_acc)} genes", flush=True)

    all_genes = set(rna_acc) | set(protein_acc)
    counts = {
        gene: len(rna_acc.get(gene, set()) | protein_acc.get(gene, set()))
        for gene in all_genes
    }
    print(f"Total: {len(counts)} genes, {time.time()-t0:.0f}s", flush=True)
    return counts


if __name__ == "__main__":
    scores = precompute_gene_cellline_counts()
    out_path = OUTPUTS_DIR / "gene_cellline_counts.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(scores, f)
    print(f"Wrote {out_path} ({len(scores)} genes)")
