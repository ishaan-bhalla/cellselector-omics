from typing import Optional
from pydantic import BaseModel, Field, field_validator

# Safety cap on multi-gene query size. NOT a feature limitation we're happy
# about — this exists because the concurrent-rank() parallelization
# (models.classical.multi_gene_ranker) was only load-tested up to 2 total
# genes (1 primary + 1 additional): that test showed cso-api memory
# spiking to ~4.43GB (57% of this VM's 7.75GB) for just 2 concurrent
# rank() calls before releasing back to baseline. How that scales to 3+
# concurrent rank() calls is UNVERIFIED on this VM's memory profile, so
# the cap is set to the largest total-gene-count that has actually been
# measured safe, not a guess. Raise this only after isolated,
# memory-capped sibling-container testing (see the pattern used for last
# night's gene_cellline_counts precompute) confirms headroom — tracked as
# future work, not done here.
MAX_ADDITIONAL_GENES = 1


class ClassicalRequest(BaseModel):
    gene: str
    # NEW: optional extra genes for combined multi-gene search (percentile-
    # normalized min() combination, see models.classical.multi_gene_ranker).
    # Empty by default — when empty, behavior is IDENTICAL to the original
    # single-gene search (see api/main.py's recommend_classical: the
    # multi-gene path is only taken when this is non-empty).
    #
    # Capped at MAX_ADDITIONAL_GENES (see comment above) — a memory-safety
    # limit, not a design choice.
    additional_genes: list[str] = Field(
        default_factory=list, max_length=MAX_ADDITIONAL_GENES
    )

    @field_validator("additional_genes", mode="before")
    @classmethod
    def _cap_additional_genes(cls, v: list[str]) -> list[str]:
        # mode="before" so this runs (and its message wins) ahead of
        # pydantic's own max_length constraint on the Field above — a
        # "before" validator sees the raw input first, whereas an "after"
        # validator would never run at all here (pydantic short-circuits
        # on the Field constraint failing first), losing our explanatory
        # message in favor of pydantic's generic "List should have at most
        # N item(s)" one. The Field(max_length=...) stays as a second,
        # redundant backstop in case this validator is ever bypassed.
        if isinstance(v, list) and len(v) > MAX_ADDITIONAL_GENES:
            raise ValueError(
                f"Too many additional genes ({len(v)}). This search supports "
                f"at most {MAX_ADDITIONAL_GENES} additional gene(s) "
                f"({MAX_ADDITIONAL_GENES + 1} total including the primary "
                "gene) — a temporary memory-safety limit on this server, "
                "not a permanent feature restriction."
            )
        return v

    disease_filter: Optional[str] = None
    lineage_filter: Optional[str] = None
    exclude_genes: list[str] = Field(default_factory=list)
    top_n: int = Field(default=10, ge=1, le=50)
    use_learned_weights: bool = True


class AgenticRequest(ClassicalRequest):
    ollama_model: str = "llama3.1:8b"
    target_cellosaurus_id: Optional[str] = None
