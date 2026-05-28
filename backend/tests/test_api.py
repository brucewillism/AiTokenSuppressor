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
async def test_compress_fast_strategy(client):
    response = await client.post(
        "/compress",
        headers=HEADERS,
        json={
            "messages": [{"role": "user", "content": "Responda em uma frase: 2+2?"}],
            "strategy": "fast",
            "use_ollama": False,
            "check_semantic_loss": False,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["strategy"] == "fast"
    assert "latency_ms" in data


@pytest.mark.asyncio
async def test_v1_models(client):
    response = await client.get("/v1/models", headers=HEADERS)
    assert response.status_code == 200
    assert response.json()["object"] == "list"
    assert len(response.json()["data"]) > 0


@pytest.mark.asyncio
async def test_v1_chat_completions_requires_auth(client):
    response = await client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "Hello"}],
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_v1_chat_completions_proxy(client, monkeypatch):
    async def fake_complete_with_fallback(
        self, messages, model=None, max_tokens=4096, temperature=0.3
    ):
        return {
            "content": "Resposta mock",
            "model": model or "groq/llama-3.3-70b-versatile",
            "provider_used": "groq",
            "tokens_input": 10,
            "tokens_output": 5,
            "cost_usd": 0,
        }

    from app.services.litellm_service import LiteLLMService

    monkeypatch.setattr(LiteLLMService, "complete_with_fallback", fake_complete_with_fallback)

    response = await client.post(
        "/v1/chat/completions",
        headers={**HEADERS, "X-ATS-Use-Ollama": "false"},
        json={
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "user", "content": "Please note that " * 50 + "we need an API."},
            ],
            "stream": False,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "chat.completion"
    assert data["choices"][0]["message"]["content"] == "Resposta mock"
    assert "X-ATS-Tokens-Before" in response.headers
    assert response.headers.get("X-ATS-Provider-Used") == "groq"


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
