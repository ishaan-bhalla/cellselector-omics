from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent

load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR = PROJECT_ROOT / "data"
GENE_EXPR_DIR = DATA_DIR / "gene expression"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
PARQUET_DIR = OUTPUTS_DIR / "parquet"
FIGURES_DIR = PROJECT_ROOT / "figures"
DOCS_DIR = PROJECT_ROOT / "docs"

FILES = {
    "hpa":      GENE_EXPR_DIR / "1_4_hpa_rna_celline.tsv",
    "depmap":   GENE_EXPR_DIR / "2_DepMap_OmicsExpressionAllGenesTPMLogp1Profile.csv",
    "geo":      GENE_EXPR_DIR / "3_GEOexpression.txt",
    "ms_ccle":  GENE_EXPR_DIR / "4_Harmonized_MS_CCLE_Gygi_subsetted.csv",
}


def setup_dirs():
    for d in (DATA_DIR, GENE_EXPR_DIR, OUTPUTS_DIR, PARQUET_DIR, FIGURES_DIR, DOCS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    print(f"Project root : {PROJECT_ROOT}")
    print(f"Gene expr dir: {GENE_EXPR_DIR}")
    print(f"Parquet dir  : {PARQUET_DIR}")
    missing = [name for name, path in FILES.items() if not path.exists()]
    if missing:
        print(f"WARNING - missing source files: {missing}")
    else:
        print("All source data files found.")


if __name__ == "__main__":
    setup_dirs()
