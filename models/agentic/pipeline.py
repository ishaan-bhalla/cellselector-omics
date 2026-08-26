from pathlib import Path
import hashlib
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config import OUTPUTS_DIR
from models.classical.ranker import rank
from models.agentic.retriever import format_context, retrieve_evidence
from models.agentic.generator import generate_comparison, generate_justification


def run(
    gene: str,
    disease_filter: str | None = None,
    lineage_filter: str | None = None,
    top_n: int = 5,
    target_cellosaurus_id: str | None = None,
    exclude_genes: list[str] | None = None,
) -> dict:
    """
    Full agentic ranking pipeline:
      1. Classical rank → top_n results (or all if target_cellosaurus_id is set)
      2. Apply exclusion-gene penalties (mirrors classical endpoint behaviour)
      3. For each: retrieve evidence, format context, generate LLM justification
      4. Generate LLM comparative summary (skipped when targeting a single cell line)
      5. Save to outputs/agentic_results_{gene}_{hash}.json

    Returns the full structured output dict.
    """
    print(f"[pipeline] Ranking {gene}"
          + (f" | disease={disease_filter}" if disease_filter else "")
          + (f" | lineage={lineage_filter}" if lineage_filter else "")
          + (f" | exclude={','.join(exclude_genes)}" if exclude_genes else "")
          + (f" | target={target_cellosaurus_id}" if target_cellosaurus_id else f" | top_n={top_n}"))

    # ── Step 1: Classical ranking ─────────────────────────────────────────────
    # When a specific cell line is requested, rank without a top_n cap so the
    # target is always present in the results before we filter down to it.
    rank_top_n = None if target_cellosaurus_id else top_n
    ranked = rank(gene, disease_filter=disease_filter,
                  lineage_filter=lineage_filter, top_n=rank_top_n)

    # ── Step 1b: Exclusion-gene penalties ────────────────────────────────────
    if ranked is not None and exclude_genes:
        from models.classical.scorer import load_mappings, score_rna_expression
        hpa_to_cvcl, _, gsm_to_cvcl = load_mappings()
        ranked = ranked.copy()
        for excl_gene in exclude_genes:
            excl_rna = score_rna_expression(excl_gene, hpa_to_cvcl, gsm_to_cvcl)
            cvcl_map = dict(zip(excl_rna["cellosaurus_id"], excl_rna["rna_score"]))
            col = f"_excl_{excl_gene}"
            ranked[col] = ranked["cellosaurus_id"].map(lambda c: float(cvcl_map.get(c, 0.0)))
            ranked["final_score"] = (ranked["final_score"] * (1 - ranked[col] * 0.5)).clip(0.0, 1.0)
        ranked = ranked.sort_values("final_score", ascending=False)

    if ranked is not None and target_cellosaurus_id:
        filtered = ranked[ranked["cellosaurus_id"] == target_cellosaurus_id]
        if len(filtered) == 0:
            print(f"[pipeline] target {target_cellosaurus_id} not found in ranked results")
        else:
            ranked = filtered

    if ranked is None or len(ranked) == 0:
        print(f"[pipeline] No results for gene: {gene}")
        return {"gene": gene, "results": [], "comparative_summary": ""}

    # ── Steps 2a–c: Per-result evidence + LLM justification ──────────────────
    results: list[dict] = []
    evidence_list: list[dict] = []

    for rank_pos, row in ranked.iterrows():
        cvcl = row["cellosaurus_id"]
        name = row.get("official_name") or cvcl
        final_score = float(row.get("final_score") or 0)

        print(f"  [{rank_pos + 1}] {name} ({cvcl}) — score={final_score:.3f}")

        # 2a: Retrieve evidence
        evidence = retrieve_evidence(gene, cvcl, row)
        evidence_list.append(evidence)

        # 2b: Format context for LLM
        context_str = format_context(gene, evidence)

        # 2c: Generate LLM justification
        try:
            justification = generate_justification(gene, context_str, name)
        except ConnectionError as exc:
            print(f"  [warning] {exc}")
            justification = str(exc)
        except Exception as exc:
            print(f"  [warning] LLM error: {exc}")
            justification = f"LLM unavailable: {exc}"

        results.append({
            "rank":           rank_pos + 1,
            "cellosaurus_id": cvcl,
            "official_name":  name,
            "scores": {
                "final_score":      final_score,
                "rna_score":        float(row.get("rna_score") or 0),
                "protein_score":    float(row.get("protein_score") or 0),
                "quality_score":    float(row.get("quality_score") or 0),
                "context_score":    float(row.get("context_score") or 0),
                "geo_confirmation": float(row.get("geo_confirmation") or 0),
            },
            "evidence":       evidence,
            "justification":  justification,
        })

    # ── Step 3: Comparative summary (skipped for single-target queries) ───────
    if target_cellosaurus_id:
        comparative_summary = ""
    else:
        print("[pipeline] Generating comparative summary...")
        try:
            comparative_summary = generate_comparison(gene, results, evidence_list)
        except ConnectionError as exc:
            comparative_summary = str(exc)
        except Exception as exc:
            comparative_summary = f"LLM unavailable: {exc}"

    # ── Step 4: Save output ───────────────────────────────────────────────────
    output = {
        "gene":               gene,
        "query": {
            "disease_filter":        disease_filter,
            "lineage_filter":        lineage_filter,
            "top_n":                 top_n,
            "target_cellosaurus_id": target_cellosaurus_id,
            "exclude_genes":         exclude_genes or [],
        },
        "results":            results,
        "comparative_summary": comparative_summary,
    }

    excl_key = "-".join(sorted(exclude_genes)) if exclude_genes else ""
    query_key = f"{gene}_{disease_filter}_{lineage_filter}_{target_cellosaurus_id}_{excl_key}"
    query_hash = hashlib.md5(query_key.encode()).hexdigest()[:8]
    out_path = OUTPUTS_DIR / f"agentic_results_{gene}_{query_hash}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"[pipeline] Saved → {out_path}")

    return output
