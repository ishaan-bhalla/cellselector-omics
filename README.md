# cellselector-omics.
Multi-omics cell line recommendation engine - University of Bristol × AstraZeneca

## Setup

```bash
git clone <repo-url>
cd cellselector-omics

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate          # macOS / Linux
# venv\Scripts\activate           # Windows

pip install -r requirements.txt

# Place the data zip in data/ and extract so that data/gene expression/ exists
# e.g. unzip cellline_data.zip -d data/

# Verify setup and create output directories
python config.py

# Inspect all four gene expression files and save Parquet snapshots
python scripts/inspect_gene_expression.py
```

Findings are appended to [docs/progress_log.md](docs/progress_log.md) with each run.
Parquet files land in `outputs/parquet/` (git-ignored).
