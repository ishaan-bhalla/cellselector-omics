import time
import warnings
from urllib import error as urllib_error
from urllib import request

_RATE_SLEEP = 0.35
_KEGG_BASE = "https://rest.kegg.jp"

# All human KEGG pathway names, fetched once per process: {hsa04010: "Cell cycle"}
_ALL_PATHWAY_NAMES: dict[str, str] | None = None


def _kegg_get(endpoint: str) -> str | None:
    url = f"{_KEGG_BASE}/{endpoint}"
    try:
        with request.urlopen(url, timeout=10) as resp:
            return resp.read().decode("utf-8")
    except (urllib_error.URLError, OSError) as exc:
        warnings.warn(f"[pathways] KEGG request failed ({url}): {exc}")
        return None


def _ensure_pathway_names() -> dict[str, str]:
    """Fetch and cache all human KEGG pathway names (one HTTP request per process)."""
    global _ALL_PATHWAY_NAMES
    if _ALL_PATHWAY_NAMES is not None:
        return _ALL_PATHWAY_NAMES

    text = _kegg_get("list/pathway/hsa")
    names: dict[str, str] = {}
    if text:
        for line in text.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                pid = parts[0].strip()  # e.g. "hsa04010"
                raw = parts[1].strip()
                names[pid] = raw.split(" - ")[0].strip()  # drop " - Homo sapiens (human)"
    _ALL_PATHWAY_NAMES = names
    return names


def _find_kegg_gene_id(gene: str) -> str | None:
    """Return the KEGG human gene ID (e.g. 'hsa:7157') for a gene symbol."""
    text = _kegg_get(f"find/hsa/{gene}")
    if not text:
        return None
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        kegg_id = parts[0].strip()
        # desc format: "TP53, tumor protein p53; K04451"
        symbols = [s.strip().upper() for s in parts[1].split(";")[0].split(",")]
        if gene.upper() in symbols:
            return kegg_id
    # Fall back to first hit
    first_line = text.splitlines()[0].split("\t")[0].strip()
    return first_line if first_line else None


def get_kegg_pathways(gene: str) -> list[dict]:
    """
    Return KEGG pathways for a human gene symbol.

    Each dict: { id, name, url }
    Returns [] if KEGG is unreachable or the gene is not found.
    """
    name_map = _ensure_pathway_names()

    time.sleep(_RATE_SLEEP)
    kegg_id = _find_kegg_gene_id(gene)
    if not kegg_id:
        warnings.warn(f"[pathways] Gene not found in KEGG: {gene}")
        return []

    time.sleep(_RATE_SLEEP)
    pathway_text = _kegg_get(f"link/pathway/{kegg_id}")
    if not pathway_text:
        return []

    # Each line: "hsa:7157\tpath:hsa04110"
    pathways: list[dict] = []
    for line in pathway_text.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        pid_raw = parts[1].strip()  # "path:hsa04110"
        if not pid_raw.startswith("path:"):
            continue
        pid = pid_raw[5:]  # "hsa04110"
        pathways.append({
            "id":   pid,
            "name": name_map.get(pid, pid),
            "url":  f"https://www.kegg.jp/pathway/{pid}",
        })

    return pathways[:20]
