from typing import Optional
from pydantic import BaseModel, Field


class ClassicalRequest(BaseModel):
    gene: str
    # NEW: optional extra genes for combined multi-gene search (percentile-
    # normalized min() combination, see models.classical.multi_gene_ranker).
    # Empty by default — when empty, behavior is IDENTICAL to the original
    # single-gene search (see api/main.py's recommend_classical: the
    # multi-gene path is only taken when this is non-empty).
    additional_genes: list[str] = Field(default_factory=list)
    disease_filter: Optional[str] = None
    lineage_filter: Optional[str] = None
    exclude_genes: list[str] = Field(default_factory=list)
    top_n: int = Field(default=10, ge=1, le=50)
    use_learned_weights: bool = True


class AgenticRequest(ClassicalRequest):
    ollama_model: str = "llama3.1:8b"
    target_cellosaurus_id: Optional[str] = None
