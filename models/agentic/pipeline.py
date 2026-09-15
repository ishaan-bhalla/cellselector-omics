from pathlib import Path
import hashlib
import json
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config import MASTER_MERGED, OUTPUTS_DIR
from models.classical.ranker import rank
from models.classical.similarity import find_alternatives
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
    """
    Structured data-gap caveats, from the SAME data_coverage the LLM prompt
    gets (retriever section 6b) so the JSON's notes and the generated
    TRADE-OFFS text can't disagree. Attached to each result in run().
    """
    from models.classical.scorer import classify_gene

    notes = []
    gene = evidence.get("gene", "")
    has_mut_calls = bool(evidence.get("metadata", {}).get("has_mutations"))
    if classify_gene(gene) == "loss_of_function" and not evidence.get("mutation"):
        if has_mut_calls:
            notes.append(
                f"{gene} is a loss-of-function target; this line HAS somatic "
                f"variant calls and none damage {gene} — likely wild-type, a "
                f"control rather than a disease model"
            )
        else:
            notes.append(
                f"{gene} is a loss-of-function target, but this line has NO "
                f"somatic variant calls — its {gene} mutation status is UNKNOWN, "
                f"not confirmed wild-type"
            )
    if not has_mut_calls:
        notes.append(
            "No somatic variant calls for this cell line — mutation-status "
            "claims (wild-type or mutant) cannot be made from this data"
        )

    cov = evidence.get("data_coverage", {})
    missing = [src for src, c in cov.items() if not c["present"]]
    if missing:
        notes.append("Missing evidence sources for this gene/cell-line pair: "
                     + ", ".join(missing))
    if not cov.get("HPA RNA expression", {}).get("present") \
            and not cov.get("DepMap RNA expression", {}).get("present"):
        notes.append("No primary RNA expression data (HPA and DepMap both absent)")

    if evidence.get("scores", {}).get("geo_confirmation", 0) < 0:
        notes.append("GEO data contradicts primary RNA sources — treat with caution")
    if not evidence.get("literature"):
        notes.append("No PubMed literature found for this gene/cell-line pair")
    return notes


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
         exclude_genes penalties are applied inside rank() itself.
      2. Filter to target cell line if target_cellosaurus_id is set.
      3. For each: retrieve evidence, format context, generate LLM justification.
      4. Generate LLM comparative summary (skipped when targeting a single cell line).
      5. Save to outputs/agentic_results_{gene}_{hash}.json.

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
                  lineage_filter=lineage_filter, top_n=rank_top_n,
                  exclude_genes=exclude_genes)

    if ranked is not None and target_cellosaurus_id:
        filtered = ranked[ranked["cellosaurus_id"] == target_cellosaurus_id]
        if len(filtered) == 0:
            print(f"[pipeline] target {target_cellosaurus_id} not found in ranked results")
        else:
            ranked = filtered

    if ranked is None or len(ranked) == 0:
        print(f"[pipeline] No results for gene: {gene}")
        return {"gene": gene, "results": [], "comparative_summary": ""}

    # ── Compute similarity-based alternatives (once, for all ranked lines) ────
    print("[pipeline] Computing similarity alternatives...")
    try:
        alternatives_map = find_alternatives(
            gene, ranked, MASTER_MERGED, top_k=3,
            disease_filter=disease_filter,
            lineage_filter=lineage_filter,
        )
    except Exception as exc:
        print(f"  [warning] similarity failed: {exc}")
        alternatives_map = {}

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

        # 2b: Format context for LLM; append exclusion warnings when relevant
        context_str = format_context(gene, evidence)

        exclusion_info = {"excluded_genes": exclude_genes or [], "warnings": []}
        if exclude_genes:
            excl_lines = []
            for excl_gene in exclude_genes:
                score = float(row.get(f"excluded_{excl_gene}_score", 0) or 0)
                if score > 0.5:
                    msg = (
                        f"EXCLUSION WARNING: This cell line also expresses "
                        f"{excl_gene} (score={score:.2f}) which was requested "
                        f"to be excluded. This may confound experimental results."
                    )
                    excl_lines.append(msg)
                    exclusion_info["warnings"].append(
                        f"{excl_gene} expressed at score {score:.2f} — may confound results"
                    )
            if excl_lines:
                context_str += "\n\n" + "\n".join(excl_lines)

        # 2c: Generate LLM justification
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
            "hpa_evidence":        row.get("hpa_evidence"),
            "depmap_evidence":     row.get("depmap_evidence"),
            "geo_evidence":        row.get("geo_evidence"),
            "protein_evidence":    row.get("protein_evidence"),
            "vs_next_rank":        row.get("vs_next_rank"),
            "quality_explanation": row.get("quality_explanation") or "",
            "context_explanation": row.get("context_explanation") or "",
            "scores": {
                "final_score":      final_score,
                "rna_score":        float(row.get("rna_score") or 0),
                "protein_score":    float(row.get("protein_score") or 0),
                "quality_score":    float(row.get("quality_score") or 0),
                "context_score":    float(row.get("context_score") or 0),
                "geo_confirmation": float(row.get("geo_confirmation") or 0),
                "pathway_activity_score": float(row.get("pathway_activity_score") or 0),
            },
            "evidence":       evidence,
            "justification":  justification,
            "verification_notes": _verification_notes(evidence),
            "data_coverage":  evidence.get("data_coverage", {}),
            "exclusion_info": exclusion_info,
            "alternatives":   alternatives_map.get(cvcl, []),
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


def run_multi_gene(
    genes: list[str],
    disease_filter: str | None = None,
    lineage_filter: str | None = None,
    top_n: int = 5,
    target_cellosaurus_id: str | None = None,
    exclude_genes: list[str] | None = None,
) -> dict:
    """
    Multi-gene analog of run(): combined classical ranking
    (multi_gene_ranker.rank_multi_gene), combined-feature-vector
    alternatives (similarity.find_alternatives_multi_gene — see its
    docstring for the design decision on how the feature vector combines
    across genes), and ONE joint LLM justification per cell line
    addressing ALL queried genes together
    (generator.generate_multi_gene_justification).

    Per-gene evidence retrieval is NOT reimplemented — retrieve_evidence()
    and format_context() (the same functions run() uses) are called once
    per gene per cell line, exactly as they already work; only the
    combining (prompt construction, citation dedup, output shape) is new.

    Scope decision: unlike run(), this does NOT generate a
    comparative_summary across results — generate_comparison()'s prompt
    template assumes a single gene's scores; extending it for multi-gene
    wasn't asked for and isn't done here (comparative_summary is always
    "" in the returned output). Flagged, not silently dropped.

    Returns the same overall shape run() does, with "genes" (list) in
    place of "gene" (str), and each result carrying combined_score /
    per_gene_percentiles / per_gene_scores / evidence_by_gene /
    verification_notes_by_gene instead of run()'s single-gene score/
    evidence/verification_notes fields.
    """
    from models.classical.multi_gene_ranker import rank_multi_gene
    from models.classical.similarity import find_alternatives_multi_gene
    from models.agentic.generator import generate_multi_gene_justification

    print(f"[pipeline] Multi-gene ranking {'+'.join(genes)}"
          + (f" | disease={disease_filter}" if disease_filter else "")
          + (f" | lineage={lineage_filter}" if lineage_filter else "")
          + (f" | exclude={','.join(exclude_genes)}" if exclude_genes else "")
          + (f" | target={target_cellosaurus_id}" if target_cellosaurus_id else f" | top_n={top_n}"))

    # ── Step 1: Combined classical ranking ────────────────────────────────────
    rank_top_n = None if target_cellosaurus_id else top_n
    combined = rank_multi_gene(genes, disease_filter, lineage_filter, exclude_genes, rank_top_n)

    if combined is not None and target_cellosaurus_id:
        filtered = combined[combined["cellosaurus_id"] == target_cellosaurus_id]
        if len(filtered) == 0:
            print(f"[pipeline] target {target_cellosaurus_id} not found in combined results")
        else:
            combined = filtered

    if combined is None or len(combined) == 0:
        print(f"[pipeline] No combined results for genes: {genes}")
        return {"genes": genes, "results": [], "comparative_summary": ""}

    # ── Combined-feature-vector similarity alternatives (once, for all
    # ranked lines) — reuses rank_multi_gene's own already-computed
    # full_scores_by_gene (see its docstring) instead of a third redundant
    # rescoring pass per gene.
    print("[pipeline] Computing combined similarity alternatives...")
    full_scores_by_gene = combined.attrs.get("full_scores_by_gene", {})
    try:
        alternatives_map = find_alternatives_multi_gene(
            genes, combined["cellosaurus_id"].tolist(), MASTER_MERGED, top_k=3,
            disease_filter=disease_filter, lineage_filter=lineage_filter,
            full_scores_by_gene=full_scores_by_gene,
        )
    except Exception as exc:
        print(f"  [warning] multi-gene similarity failed: {exc}")
        alternatives_map = {}

    # ── Steps 2a-c: per-result, per-gene evidence + ONE joint justification ──
    results: list[dict] = []
    evidence_list: list[dict] = []  # one {gene: evidence} dict per result

    for rank_pos, row in combined.iterrows():
        cvcl = row["cellosaurus_id"]
        name = row.get("official_name") or cvcl
        combined_score = float(row.get("combined_score") or 0)

        print(f"  [{rank_pos + 1}] {name} ({cvcl}) — combined_score={combined_score:.3f}")

        # 2a: Retrieve evidence PER GENE, reusing retrieve_evidence()
        # unmodified — each gene needs its OWN scored row (hpa_score/
        # depmap_score/etc genuinely differ per gene), sourced from
        # rank_multi_gene's full_scores_by_gene; `row` (the combined
        # result) is the fallback only for a gene whose full frame is
        # unavailable, since it still has cellosaurus_id/official_name/
        # disease/lineage — enough for retrieve_evidence not to crash,
        # just without that gene's own score columns.
        evidence_by_gene: dict[str, dict] = {}
        context_by_gene: dict[str, str] = {}
        for gene in genes:
            gene_full = full_scores_by_gene.get(gene)
            gene_row = row
            if gene_full is not None:
                match = gene_full[gene_full["cellosaurus_id"] == cvcl]
                if len(match) > 0:
                    gene_row = match.iloc[0]
            evidence = retrieve_evidence(gene, cvcl, gene_row)
            evidence_by_gene[gene] = evidence
            context_by_gene[gene] = format_context(gene, evidence)

        evidence_list.append(evidence_by_gene)

        # 2b/2c: ONE combined prompt, ONE joint justification
        try:
            justification = generate_multi_gene_justification(genes, context_by_gene, name)
        except ConnectionError as exc:
            print(f"  [warning] {exc}")
            justification = str(exc)
        except Exception as exc:
            print(f"  [warning] LLM error: {exc}")
            justification = f"LLM unavailable: {exc}"

        # Citations: union across all queried genes' evidence, deduplicated
        # (by dataset name / PMID) before handing to
        # add_citations_to_justification() UNMODIFIED — it just needs flat
        # lists, same as the single-gene path.
        all_dataset_cites: list[dict] = []
        seen_ds: set[str] = set()
        all_papers: list[dict] = []
        seen_pmids: set[str] = set()
        for gene in genes:
            ev = evidence_by_gene[gene]
            for c in ev.get("dataset_citations", []):
                if c["name"] not in seen_ds:
                    seen_ds.add(c["name"])
                    all_dataset_cites.append(c)
            for p in ev.get("literature", []):
                if p["pmid"] not in seen_pmids:
                    seen_pmids.add(p["pmid"])
                    all_papers.append(p)

        justification = add_citations_to_justification(
            justification, all_dataset_cites, all_papers,
        )

        results.append({
            "rank":                 rank_pos + 1,
            "cellosaurus_id":       cvcl,
            "official_name":        name,
            "combined_score":       combined_score,
            "per_gene_percentiles": row.get("per_gene_percentiles"),
            "per_gene_scores":      row.get("per_gene_scores"),
            "evidence_by_gene":     evidence_by_gene,
            "justification":        justification,
            # Per-gene, not merged into one list — a caller can verify
            # EACH gene's mandatory mutation-status/missing-sources
            # statement was actually addressed, not just assume the LLM
            # covered both from a single blended list (see STEP 4).
            "verification_notes_by_gene": {
                gene: _verification_notes(evidence_by_gene[gene]) for gene in genes
            },
            "alternatives": alternatives_map.get(cvcl, []),
        })

    # ── Step 3: comparative summary — NOT generated for multi-gene (see
    # docstring's scope decision). Always empty here, not silently omitted.
    comparative_summary = ""

    # ── Step 4: Save output ───────────────────────────────────────────────────
    output = {
        "genes": genes,
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

    genes_key = "-".join(genes)
    excl_key = "-".join(sorted(exclude_genes)) if exclude_genes else ""
    query_key = f"{genes_key}_{disease_filter}_{lineage_filter}_{target_cellosaurus_id}_{excl_key}"
    query_hash = hashlib.md5(query_key.encode()).hexdigest()[:8]
    out_path = OUTPUTS_DIR / f"agentic_results_multi_{genes_key}_{query_hash}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"[pipeline] Saved → {out_path}")

    return output
