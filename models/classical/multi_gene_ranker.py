from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from models.classical.ranker import rank

# ─────────────────────────────────────────────────────────────────────────────
# Multi-gene combined search: "which cell lines are good candidates for
# studying ALL of these genes together?" (e.g. a double-mutant or combo-
# therapy context). Percentile-normalized min() combination — NOT a raw
# final_score average — because final_score's distribution is gene-class-
# dependent (a loss_of_function gene's scores cluster near {0, 1} via the
# mutation-primary formula; a tissue_specific gene's scores spread smoothly
# across the expression range). Averaging raw scores would let whichever
# gene has the widest spread dominate the combined ranking. Percentile-
# ranking each gene's final_score WITHIN ITS OWN candidate distribution
# first puts every gene on the same 0-1 "how good is this line, relative to
# every other candidate for THIS gene" scale before combining — min() then
# rewards a line only if it's a strong candidate for EVERY queried gene,
# not just the highest-spread one (see rank_multi_gene's docstring and
# STEP 4's cross-class verification in the task report).
# ─────────────────────────────────────────────────────────────────────────────


def rank_multi_gene(
    genes: list[str],
    disease_filter: str | None = None,
    lineage_filter: str | None = None,
    exclude_genes: list[str] | None = None,
    top_n: int | None = None,
) -> pd.DataFrame:
    """
    Combine rankings across multiple genes via percentile-normalized min()
    combination.

    For each gene independently:
    1. Run the existing, already-validated rank() function (reused exactly
       as-is, weights=None/use_learned_weights=False — i.e. rank()'s own
       normal defaults, identical to what a plain single-gene call gets —
       with top_n=None so every candidate is included: percentile rank
       must be computed over the FULL per-gene candidate distribution, not
       a top-N-truncated slice, or it would be a different, wrong number).
    2. Convert each cell line's final_score to a percentile within that
       gene's own candidate distribution (.rank(pct=True)).

    Then combine:
    3. Inner-join across all per-gene result sets on cellosaurus_id (a line
       must have data for EVERY queried gene to get a combined_score —
       min() is undefined otherwise) and take combined_score =
       min(percentile_gene1, percentile_gene2, ...).
    4. Sort by combined_score descending — kind="stable" so that for
       len(genes) == 1 (combined_score is then a monotonic rescaling of
       that one gene's final_score) tie-break order EXACTLY matches
       rank()'s own multi-key tie-break, not just "usually the same order".
    5. per_gene_percentiles / per_gene_scores (raw final_score) are
       attached per row as {gene: value} dicts, so the caller (the API,
       the UI) can show why a line ranked where it did — same evidence-
       auditability standard as every other scorer in this project.

    Cell lines missing data for ANY queried gene are excluded from the
    combined result (min() has no input for them) — the number excluded
    this way is returned via the DataFrame's .attrs (pandas' own mechanism
    for attaching run metadata that isn't itself a row), not as a column,
    since it describes the whole query, not any one row:
        result.attrs["n_excluded_missing_data"]  — int
        result.attrs["total_candidates_per_gene"] — {gene: int}
        result.attrs["genes"]                     — list[str], input order

    Returns columns: cellosaurus_id, official_name, disease, lineage,
        combined_score, per_gene_percentiles, per_gene_scores,
        pct_<gene> / raw_<gene> per queried gene (the same data the dict
        columns carry, unpacked — convenient for anything that wants to
        avoid dict columns, e.g. a quick to_string() or a CSV export).
    """
    if not genes:
        raise ValueError("rank_multi_gene requires at least one gene")

    # De-duplicate while preserving order (a caller accidentally repeating
    # a gene shouldn't silently give it double weight in the min()).
    seen: set[str] = set()
    genes = [g for g in genes if not (g in seen or seen.add(g))]

    per_gene: dict[str, pd.DataFrame] = {}
    total_candidates_per_gene: dict[str, int] = {}
    all_seen_lines: set[str] = set()

    for gene in genes:
        df = rank(
            gene,
            disease_filter=disease_filter,
            lineage_filter=lineage_filter,
            top_n=None,  # full candidate distribution — see docstring
            exclude_genes=exclude_genes,
        )
        df = df[["cellosaurus_id", "official_name", "disease", "lineage",
                  "final_score"]].copy()
        df["pct"] = df["final_score"].rank(pct=True, method="average")
        per_gene[gene] = df
        total_candidates_per_gene[gene] = len(df)
        all_seen_lines |= set(df["cellosaurus_id"])

    # Inner-merge across all genes on cellosaurus_id — base_gene's row
    # order (already rank()'s own tie-broken sort) is preserved through
    # the merges below (pandas merge with how="inner" keeps the LEFT
    # frame's row order for matching keys), which is what makes the
    # kind="stable" sort in the single-gene case exactly reproduce
    # rank()'s own tie-break order rather than merely approximating it.
    base_gene = genes[0]
    result = per_gene[base_gene][["cellosaurus_id"]].copy()
    for gene in genes:
        g_cols = per_gene[gene][["cellosaurus_id", "final_score", "pct"]].rename(
            columns={"final_score": f"raw_{gene}", "pct": f"pct_{gene}"}
        )
        result = result.merge(g_cols, on="cellosaurus_id", how="inner")

    n_included = len(result)
    n_excluded_missing_data = len(all_seen_lines) - n_included

    meta = (
        per_gene[base_gene][["cellosaurus_id", "official_name", "disease", "lineage"]]
        .drop_duplicates(subset="cellosaurus_id")
    )
    result = result.merge(meta, on="cellosaurus_id", how="left")

    pct_cols = [f"pct_{g}" for g in genes]
    raw_cols = [f"raw_{g}" for g in genes]
    result["combined_score"] = result[pct_cols].min(axis=1)

    result["per_gene_percentiles"] = result.apply(
        lambda row: {g: round(float(row[f"pct_{g}"]), 4) for g in genes}, axis=1
    )
    result["per_gene_scores"] = result.apply(
        lambda row: {g: round(float(row[f"raw_{g}"]), 4) for g in genes}, axis=1
    )

    # kind="stable" (mergesort): see docstring point 4 — required for the
    # single-gene case to reproduce rank()'s exact tie-break order, not an
    # incidental default.
    result = result.sort_values(
        "combined_score", ascending=False, kind="stable"
    ).reset_index(drop=True)

    if top_n is not None:
        result = result.head(top_n)

    out_cols = (
        ["cellosaurus_id", "official_name", "disease", "lineage",
         "combined_score", "per_gene_percentiles", "per_gene_scores"]
        + pct_cols + raw_cols
    )
    result = result[out_cols].reset_index(drop=True)

    result.attrs["n_excluded_missing_data"] = n_excluded_missing_data
    result.attrs["total_candidates_per_gene"] = total_candidates_per_gene
    result.attrs["genes"] = list(genes)
    return result


if __name__ == "__main__":
    print("Multi-gene self-test (BRCA1 + EGFR)...")
    r = rank_multi_gene(["BRCA1", "EGFR"], top_n=10)
    print(r[["official_name", "cellosaurus_id", "combined_score"]].to_string())
    print()
    print(f"Excluded (missing data for >=1 gene): {r.attrs['n_excluded_missing_data']}")
    print(f"Total candidates per gene: {r.attrs['total_candidates_per_gene']}")
