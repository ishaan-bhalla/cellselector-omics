from pathlib import Path
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
) -> dict:
    """
    Full agentic ranking pipeline:
      1. Classical rank → top_n results
      2. For each: retrieve evidence, format context, generate LLM justification
      3. Generate LLM comparative summary
      4. Save to outputs/agentic_results_{gene}.json

    Returns the full structured output dict.
    """
    print(f"[pipeline] Ranking {gene}"
          + (f" | disease={disease_filter}" if disease_filter else "")
          + (f" | lineage={lineage_filter}" if lineage_filter else "")
          + f" | top_n={top_n}")

    # ── Step 1: Classical ranking ─────────────────────────────────────────────
    ranked = rank(gene, disease_filter=disease_filter,
                  lineage_filter=lineage_filter, top_n=top_n)

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

    # ── Step 3: Comparative summary ───────────────────────────────────────────
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
            "disease_filter":  disease_filter,
            "lineage_filter":  lineage_filter,
            "top_n":           top_n,
        },
        "results":            results,
        "comparative_summary": comparative_summary,
    }

    out_path = OUTPUTS_DIR / f"agentic_results_{gene}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"[pipeline] Saved → {out_path}")

    return output
