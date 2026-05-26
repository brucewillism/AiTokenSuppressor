"""Basic API tests."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

API_KEY = "ats-dev-api-key"
HEADERS = {"X-API-Key": API_KEY}


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_compress_requires_auth(client):
    response = await client.post("/compress", json={
        "messages": [{"role": "user", "content": "Hello world"}]
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_compress_with_api_key(client):
    response = await client.post(
        "/compress",
        headers=HEADERS,
        json={
            "messages": [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Hello " * 100},
            ],
            "strategy": "balanced",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "tokens_before" in data
    assert "tokens_after" in data
    assert data["tokens_after"] <= data["tokens_before"]


@pytest.mark.asyncio
async def test_analyze(client):
    response = await client.post(
        "/analyze",
        headers=HEADERS,
        json={
            "messages": [{"role": "user", "content": "Implement a REST API in Python"}],
            "target_model": "claude-3-5-sonnet",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "complexity_score" in data
    assert "recommended_strategy" in data
