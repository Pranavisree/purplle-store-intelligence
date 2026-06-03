# PROMPT:
# Generate basic FastAPI endpoint tests

# CHANGES MADE:
# Modified assertions based on my API responses

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200

def test_metrics():
    response = client.get("/metrics")
    assert response.status_code == 200

def test_funnel():
    response = client.get("/funnel")
    assert response.status_code == 200

def test_heatmap():
    response = client.get("/heatmap")
    assert response.status_code == 200