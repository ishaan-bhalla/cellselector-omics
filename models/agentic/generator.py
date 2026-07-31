from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

try:
    import ollama
    _OLLAMA_AVAILABLE = True
except ImportError:
    _OLLAMA_AVAILABLE = False   

_MODEL_PRIMARY = "llama3.1:8b"
_MODEL_FALLBACK = "llama3:latest"    # used when primary is OOM-killed
_MODEL = _MODEL_PRIMARY

SYSTEM_PROMPT = """You are a bioinformatics assistant helping scientists at \
AstraZeneca select cell lines for experiments. You are given structured \
evidence about a cell line's suitability for studying a specific gene. \
Your job is to:
1. Explain WHY this cell line is or isn't suitable
2. Highlight the strongest evidence
3. Flag any trade-offs or concerns
4. Suggest what type of experiment it suits best
Be concise, precise, and scientifically accurate. Use plain English that \
a bench scientist can act on. Never make up data — only use what is provided."""


def _chat(prompt: str) -> str:
    """Send a prompt to ollama and return the response string.

    Tries _MODEL_PRIMARY first; if the model is OOM-killed falls back to
    _MODEL_FALLBACK automatically (llama4:scout needs ~67 GB RAM).
    """
    if not _OLLAMA_AVAILABLE:
        raise RuntimeError(
            "ollama Python package not installed. Run: pip install ollama"
        )

    msgs = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": prompt},
    ]

    for model in (_MODEL_PRIMARY, _MODEL_FALLBACK):
        try:
            response = ollama.chat(model=model, messages=msgs)
            if model != _MODEL_PRIMARY:
                print(f"  [generator] Using fallback model: {model}")
            return response["message"]["content"]
        except Exception as exc:
            err = str(exc)
            if "connection" in err.lower() or "refused" in err.lower():
                raise ConnectionError(
                    "Cannot reach ollama. Start it with: ollama serve"
                ) from exc
            if "killed" in err.lower() or "500" in err or "terminated" in err.lower():
                # OOM or crash — try next model
                print(f"  [generator] {model} failed (likely OOM), trying fallback...")
                continue
            raise

    raise RuntimeError(
        f"All models failed. Primary: {_MODEL_PRIMARY}, Fallback: {_MODEL_FALLBACK}"
    )


def generate_justification(
    gene: str,
    evidence_context: str,
    cell_line_name: str,
) -> str:
    """
    Generate a structured justification for whether a cell line is suitable
    for studying the given gene.
    """
    prompt = f"""Based on this evidence, justify whether {cell_line_name} is a \
good choice for studying {gene}:

{evidence_context}

Provide your answer in exactly this format:
1. RECOMMENDATION: (Strongly Recommended / Recommended / Use with Caution / Not Recommended)
2. KEY REASON: (one sentence — the single most important factor)
3. EVIDENCE SUMMARY: (2-3 sentences on the expression data)
4. TRADE-OFFS: (any concerns or limitations to flag)
5. BEST FOR: (what experiment type suits this cell line best)"""

    return _chat(prompt)


def add_citations_to_justification(
    justification_text: str,
    dataset_citations: list[dict],
    literature: list[dict],
) -> str:
    """
    Append structured DATA SOURCES (section 6) and LITERATURE (section 7) blocks
    to LLM-generated justification text.

    Citations are built deterministically from evidence data rather than relying
    on the LLM to format them, which was unreliable.
    """
    citations_block = "\n\n6. DATA SOURCES:\n"
    for i, c in enumerate(dataset_citations, 1):
        citations_block += f"[D{i}] {c['name']}\n"
        citations_block += f"     {c['citation']}\n"
        citations_block += f"     PMID:{c['pmid']}\n"
        citations_block += f"     {c['url']}\n\n"

    citations_block += "\n7. LITERATURE:\n"
    for i, p in enumerate(literature, 1):
        citations_block += (
            f"[P{i}] {p['authors']} ({p['year']}). "
            f"{p['title']}.\n"
            f"      PMID:{p['pmid']} | {p['url']}\n\n"
        )

    return justification_text + citations_block


def generate_comparison(
    gene: str,
    top_results: list[dict],
    evidence_list: list[dict],
) -> str:
    """
    Generate a comparative summary across the top recommended cell lines.
    """
    lines = [f"TOP RECOMMENDATIONS FOR {gene}:"]
    for i, (res, ev) in enumerate(zip(top_results, evidence_list), 1):
        name    = res.get("official_name", res.get("cellosaurus_id", "?"))
        score   = res.get("scores", {}).get("final_score", 0)
        rna     = res.get("scores", {}).get("rna_score", 0)
        quality = res.get("scores", {}).get("quality_score", 0)
        disease = ev.get("metadata", {}).get("disease", "unknown")
        lines.append(
            f"  {i}. {name} — final={score:.2f}, RNA={rna:.2f}, "
            f"quality={quality:.2f}, disease={disease}"
        )

    summary_prompt = (
        "\n".join(lines)
        + f"\n\nIn 3-4 sentences, compare these options for studying {gene}. "
        "Highlight which offers the best expression evidence, which has the "
        "best data completeness, and whether any specific cell line stands out "
        "for a particular experimental context. Be direct and practical."
    )

    return _chat(summary_prompt)
