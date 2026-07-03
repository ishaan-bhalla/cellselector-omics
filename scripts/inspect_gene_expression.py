import sys
from pathlib import Path
from datetime import datetime

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import FILES, PARQUET_DIR, setup_dirs

setup_dirs()

ENSEMBL_PREFIXES = ("ENSG", "ENSMUSG")
ENTREZ_LIKE = lambda s: str(s).isdigit()
HGNC_LIKE = lambda s: str(s).isupper() and str(s).isalpha() and 2 <= len(str(s)) <= 20

ACH_LIKE = lambda s: str(s).startswith("ACH-")
CVCL_LIKE = lambda s: str(s).startswith("CVCL_")


def _detect_id_type(series: pd.Series) -> str:
    sample = series.dropna().astype(str).head(20)
    if sample.str.startswith(ENSEMBL_PREFIXES[0]).any() or sample.str.startswith(ENSEMBL_PREFIXES[1]).any():
        return "Ensembl gene ID"
    if sample.apply(ACH_LIKE).any():
        return "DepMap ACH cell line ID"
    if sample.apply(CVCL_LIKE).any():
        return "Cellosaurus CVCL cell line ID"
    if sample.apply(ENTREZ_LIKE).all():
        return "possible Entrez gene ID (numeric)"
    if sample.apply(HGNC_LIKE).mean() > 0.7:
        return "possible HGNC gene symbol"
    return "unknown"


def _sniff_sep(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".tsv":
        return "\t"
    if suffix in (".csv",):
        return ","
    # For .txt, peek at the first line
    with open(path, encoding="utf-8", errors="replace") as f:
        first = f.readline()
    if first.count("\t") > first.count(","):
        return "\t"
    return ","


def inspect_file(name: str, path: Path) -> dict:
    print(f"\n{'='*60}")
    print(f"  {name}  ->  {path.name}")
    print(f"{'='*60}")

    sep = _sniff_sep(path)
    sep_label = "TAB" if sep == "\t" else "COMMA"
    print(f"Detected separator : {sep_label}")

    try:
        preview = pd.read_csv(path, sep=sep, nrows=5, low_memory=False)
    except Exception as exc:
        print(f"ERROR reading preview: {exc}")
        return {"name": name, "status": "error", "error": str(exc)}

    try:
        full = pd.read_csv(path, sep=sep, low_memory=False)
    except Exception as exc:
        print(f"ERROR reading full file: {exc}")
        return {"name": name, "status": "error", "error": str(exc)}

    print(f"\nShape              : {full.shape[0]:,} rows x {full.shape[1]:,} columns")
    print(f"\nColumn names ({len(full.columns)}):")
    for col in full.columns:
        print(f"  {col}")

    print("\nDtypes:")
    print(full.dtypes.to_string())

    print("\nHead (3 rows):")
    print(full.head(3).to_string())

    first_col = full.columns[0]
    print(f"\nSample values from first column '{first_col}':")
    print(full[first_col].head(10).to_list())

    id_type = _detect_id_type(full[first_col])
    print(f"\nFirst column ID type : {id_type}")

    # Check all columns for known ID patterns
    flagged = {}
    for col in full.columns:
        t = _detect_id_type(full[col])
        if t != "unknown":
            flagged[col] = t
    if flagged:
        print("\nFlagged ID-like columns:")
        for col, t in flagged.items():
            print(f"  '{col}' -> {t}")

    # Save as Parquet
    parquet_path = PARQUET_DIR / f"{name}.parquet"
    if parquet_path.exists():
        print(f"\nParquet already exists, skipping: {parquet_path.name}")
    else:
        full.to_parquet(parquet_path, index=False)
        print(f"\nSaved Parquet -> {parquet_path}")

    return {
        "name": name,
        "status": "ok",
        "shape": full.shape,
        "sep": sep_label,
        "first_col": first_col,
        "first_col_id_type": id_type,
        "flagged_id_cols": flagged,
        "parquet": str(parquet_path),
    }


def append_progress_log(results: list[dict]):
    log_path = Path(__file__).resolve().parent.parent / "docs" / "progress_log.md"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"\n## Gene Expression Inspection — {timestamp}\n",
        "| File | Status | Shape | Separator | First-col ID type |\n",
        "|------|--------|-------|-----------|-------------------|\n",
    ]
    for r in results:
        shape = f"{r['shape'][0]:,} x {r['shape'][1]:,}" if r.get("shape") else "N/A"
        lines.append(
            f"| {r['name']} | {r['status']} | {shape} | {r.get('sep','?')} "
            f"| {r.get('first_col_id_type','?')} |\n"
        )
    lines.append("\n")
    with open(log_path, "a", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"\nProgress log updated -> {log_path}")


if __name__ == "__main__":
    results = []
    for name, path in FILES.items():
        if not path.exists():
            print(f"\nSKIPPING {name}: file not found at {path}")
            results.append({"name": name, "status": "missing"})
            continue
        results.append(inspect_file(name, path))

    append_progress_log(results)
    print("\nDone.")
