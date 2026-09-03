import pytest
import pandas as pd
from models.classical.scorer import (
    classify_gene, score_rna_expression, score_protein_expression,
    score_context, score_data_quality, load_mappings,
    get_gene_role, GENE_ROLES
)

class TestClassifyGene:
    """Test gene classification into tissue_specific/ubiquitous/LOF."""
    
    def test_tissue_specific_gene(self):
        """EGFR should be classified as tissue_specific."""
        assert classify_gene("EGFR") == "tissue_specific"
    
    def test_ubiquitous_gene(self):
        """TP53 should be classified as ubiquitous."""
        assert classify_gene("TP53") == "ubiquitous"
    
    def test_lof_gene(self):
        """BRCA1 should be classified as loss_of_function."""
        assert classify_gene("BRCA1") == "loss_of_function"
    
    def test_unknown_gene_defaults_to_tissue_specific(self):
        """An unknown gene should default to tissue_specific."""
        assert classify_gene("FAKEGENE123") == "tissue_specific"
    
    def test_case_insensitivity(self):
        """Gene classification should be case-insensitive."""
        assert classify_gene("egfr") == classify_gene("EGFR")


class TestGeneRole:
    """Test the gene role/category lookup."""
    
    def test_rtk(self):
        assert get_gene_role("EGFR") == "receptor tyrosine kinase"
    
    def test_tumor_suppressor(self):
        assert get_gene_role("TP53") == "tumor suppressor"
    
    def test_unknown_returns_none(self):
        assert get_gene_role("UNKNOWNGENE") is None
    
    def test_all_roles_are_strings(self):
        for gene, role in GENE_ROLES.items():
            assert isinstance(role, str), f"{gene} has non-string role"


