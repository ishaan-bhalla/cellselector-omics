import pytest
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

class TestHealthEndpoint:
    def test_health(self):
        response = client.get("/health")
        assert response.status_code == 200


class TestGeneSearch:
    def test_search_valid_gene(self):
        response = client.get("/genes/search?q=EGFR")
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0
    
    def test_search_invalid_gene(self):
        response = client.get("/genes/search?q=FAKEGENE999")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0


class TestClassicalRecommendation:
    def test_basic_recommendation(self):
        response = client.post("/recommend/classical", json={
            "gene": "EGFR",
            "top_n": 3
        })
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) <= 3
    
    def test_with_disease_filter(self):
        response = client.post("/recommend/classical", json={
            "gene": "EGFR",
            "disease_filter": "lung",
            "top_n": 5
        })
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) > 0
    
    def test_with_exclusion(self):
        response = client.post("/recommend/classical", json={
            "gene": "EGFR",
            "disease_filter": "lung",
            "exclude_genes": ["TP53"],
            "top_n": 5
        })
        assert response.status_code == 200
    
    def test_same_gene_search_and_exclude_returns_400(self):
        response = client.post("/recommend/classical", json={
            "gene": "EGFR",
            "exclude_genes": ["EGFR"],
            "top_n": 5
        })
        assert response.status_code == 400
    
    def test_response_has_session_id(self):
        response = client.post("/recommend/classical", json={
            "gene": "EGFR",
            "top_n": 3
        })
        data = response.json()
        assert "session_id" in data
    
    def test_results_have_required_fields(self):
        response = client.post("/recommend/classical", json={
            "gene": "EGFR",
            "top_n": 1
        })
        data = response.json()
        if data["results"]:
            result = data["results"][0]
            assert "cellosaurus_id" in result
            assert "final_score" in result
            assert "rna_score" in result
            assert "gene_class" in result
    
    def test_no_nan_in_response(self):
        """Regression test: NaN values must be sanitised."""
        response = client.post("/recommend/classical", json={
            "gene": "EGFR",
            "disease_filter": "lung",
            "top_n": 10
        })
        import json
        # This will throw if response contains NaN
        text = response.text
        assert "NaN" not in text
        assert "Infinity" not in text
