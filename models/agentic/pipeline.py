from pathlib import Path
import json
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config import OUTPUTS_DIR
from models.classical.ranker import rank
from models.agentic.retriever import format_context, retrieve_evidence
from models.agentic.generator import (
    add_citations_to_justification,
    generate_comparison,
    generate_justification,
)


def _parse_justification(text: str) -> dict:
    """
    Parse the numbered justification into structured fields.

    Sections 1-5 are LLM-generated prose extracted as strings.
    Sections 6 (DATA SOURCES) and 7 (LITERATURE) are appended by
    add_citations_to_justification() and parsed into lists.
    """
    key_map = {
        "1": "recommendation",
        "2": "key_reason",
        "3": "evidence_summary",
        "4": "trade_offs",
        "5": "best_for",
    }
    sections: dict = {v: "" for v in key_map.values()}
    sections["data_citations"]      = []
    sections["literature_citations"] = []

    pattern = re.compile(r"^\s*(\d)\.\s+[A-Z][A-Z\s\-]+:\s*(.*)", re.MULTILINE)
    matches = list(pattern.finditer(text))

    raw: dict[str, str] = {}
    for idx, m in enumerate(matches):
        num        = m.group(1)
        first_line = m.group(2).strip()
        start = m.end()
        end   = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        continuation = text[start:end].strip()
        content = (first_line + (" " + continuation if continuation else "")).strip()
        if num in key_map:
            sections[key_map[num]] = content
        else:
            raw[num] = content

    # Section 6: DATA SOURCES → list of "[D1] ..." strings
    raw6 = raw.get("6", "")
    if raw6:
        markers = re.findall(r'\[D\d+\]', raw6)
        entries = re.split(r'\[D\d+\]', raw6)
        for marker, entry in zip(markers, entries[1:]):
            sections["data_citations"].append(f"{marker} {entry.strip()}")

    # Section 7: LITERATURE → list of "[P1] ..." strings
    raw7 = raw.get("7", "")
    if raw7:
        markers = re.findall(r'\[P\d+\]', raw7)
        entries = re.split(r'\[P\d+\]', raw7)
        for marker, entry in zip(markers, entries[1:]):
            sections["literature_citations"].append(f"{marker} {entry.strip()}")

    return sections


def _verification_notes(evidence: dict) -> list[str]:
    """Derive data-quality caveats from evidence dict."""
    notes = []
    if not evidence.get("hpa_expression") and not evidence.get("depmap_expression"):
        notes.append("No primary RNA expression data available")
    if evidence.get("scores", {}).get("geo_confirmation", 0) < 0:
        notes.append("GEO data contradicts primary RNA sources — treat with caution")
    if not evidence.get("proteomics"):
        notes.append("No proteomics data available for this cell line")
    if not evidence.get("geo_expression"):
        notes.append("No GEO validation data found")
    if not evidence.get("literature"):
        notes.append("No PubMed literature found for this gene/cell-line pair")
    return notes


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

        # 2c: Generate LLM justification, then append deterministic citation blocks
        try:
            justification = generate_justification(gene, context_str, name)
        except ConnectionError as exc:
            print(f"  [warning] {exc}")
            justification = str(exc)
        except Exception as exc:
            print(f"  [warning] LLM error: {exc}")
            justification = f"LLM unavailable: {exc}"

        justification = add_citations_to_justification(
            justification,
            evidence.get("dataset_citations", []),
            evidence.get("literature", []),
        )

        results.append({
            "rank":                rank_pos + 1,
            "cellosaurus_id":      cvcl,
            "official_name":       name,
            "scores": {
                "final_score":      final_score,
                "rna_score":        float(row.get("rna_score") or 0),
                "protein_score":    float(row.get("protein_score") or 0),
                "quality_score":    float(row.get("quality_score") or 0),
                "context_score":    float(row.get("context_score") or 0),
                "geo_confirmation": float(row.get("geo_confirmation") or 0),
            },
            "evidence":            evidence,
            "justification":       justification,
            "justification_parsed": _parse_justification(justification),
            "literature":          evidence.get("literature", []),
            "dataset_citations":   evidence.get("dataset_citations", []),
            "verification_notes":  _verification_notes(evidence),
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
