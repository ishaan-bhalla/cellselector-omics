import time
import warnings

import requests

_RATE_SLEEP = 0.35
_KEGG_BASE = "https://rest.kegg.jp"

# All human KEGG pathway names, fetched once per process: {hsa04010: "Cell cycle"}
_ALL_PATHWAY_NAMES: dict[str, str] | None = None

# All human KEGG gene ID -> primary symbol, fetched once per process:
# {"hsa:1956": "EGFR", ...}. One bulk request replaces one request per gene,
# which is what makes resolving a whole pathway's membership (50-300+ genes)
# tractable instead of minutes of rate-limited per-gene lookups.
_ALL_GENE_SYMBOLS: dict[str, str] | None = None

# Gene symbols per pathway, fetched once per process: {hsa04012: ["EGFR", ...]}
_PATHWAY_GENES_CACHE: dict[str, list[str]] = {}


def _kegg_get(endpoint: str) -> str | None:
    url = f"{_KEGG_BASE}/{endpoint}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return None
        return resp.text
    except requests.exceptions.RequestException as exc:
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


def _ensure_gene_symbols() -> dict[str, str]:
    """Fetch and cache KEGG ID -> primary symbol for every human gene (one bulk request)."""
    global _ALL_GENE_SYMBOLS
    if _ALL_GENE_SYMBOLS is not None:
        return _ALL_GENE_SYMBOLS

    text = _kegg_get("list/hsa")
    symbols: dict[str, str] = {}
    if text:
        for line in text.splitlines():
            parts = line.split("\t")
            if len(parts) < 4:
                continue
            kid  = parts[0].strip()          # "hsa:1956"
            desc = parts[3]                  # "EGFR, ERBB, ...; epidermal growth factor receptor..."
            symbol = desc.split(";")[0].split(",")[0].strip()
            if symbol:
                symbols[kid] = symbol
    _ALL_GENE_SYMBOLS = symbols
    return symbols


def get_genes_in_pathway(pathway_id: str, max_genes: int = 200) -> list[str]:
    """
    Given a KEGG pathway ID (e.g. 'hsa04012'), return the gene symbols
    that are members of that pathway.

    Reverse of get_kegg_pathways(): that goes gene -> pathways, this goes
    pathway -> genes. Together they let a caller do a 2-hop
    gene -> pathway -> gene graph traversal.

    max_genes is a generous safety cap, not a rate-limit workaround: gene
    ID -> symbol resolution comes from one cached bulk lookup
    (_ensure_gene_symbols), so a full pathway (up to a few hundred genes)
    resolves in one additional request, not one request per gene.
    """
    symbol_map = _ensure_gene_symbols()

    text = _kegg_get(f"link/hsa/{pathway_id}")
    if not text:
        return []

    # Each line: "path:hsa04012\thsa:1956"
    kegg_gene_ids: list[str] = []
    for line in text.strip().splitlines():
        parts = line.split("\t")
        if len(parts) == 2:
            kegg_gene_ids.append(parts[1].strip())

    gene_symbols: list[str] = []
    for kid in kegg_gene_ids:
        symbol = symbol_map.get(kid)
        if symbol:
            gene_symbols.append(symbol)
        if len(gene_symbols) >= max_genes:
            break

    return gene_symbols


def get_cached_pathway_genes(pathway_id: str) -> list[str]:
    if pathway_id not in _PATHWAY_GENES_CACHE:
        _PATHWAY_GENES_CACHE[pathway_id] = get_genes_in_pathway(pathway_id)
    return _PATHWAY_GENES_CACHE[pathway_id]
