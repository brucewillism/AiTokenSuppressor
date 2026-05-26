#!/usr/bin/env python3
"""Example script demonstrating AI Token Suppressor API usage."""

import asyncio
import json

import httpx

API_URL = "http://localhost:8000"
API_KEY = "ats-dev-api-key-change-in-production"
HEADERS = {"X-API-Key": API_KEY, "Content-Type": "application/json"}


async def demo_compress():
    messages = [
        {"role": "system", "content": "You are a senior Python developer."},
        {"role": "user", "content": (
            "Please note that it is important to remember that we need to implement "
            "a REST API with FastAPI. The API should include authentication using JWT, "
            "database models with SQLAlchemy, proper error handling, and comprehensive "
            "logging. Please note that it is important to remember that we also need "
            "rate limiting and input validation using Pydantic models."
        )},
    ]

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            f"{API_URL}/compress",
            headers=HEADERS,
            json={"messages": messages, "strategy": "aggressive"},
        )
        data = response.json()
        print("=== COMPRESS RESULT ===")
        print(f"Tokens before: {data['tokens_before']}")
        print(f"Tokens after:  {data['tokens_after']}")
        print(f"Savings:       {data['savings_percent']}%")
        print(f"Operations:    {data['operations_applied']}")
        print()


async def demo_optimize():
    messages = [
        {"role": "user", "content": "Design a microservices architecture for an e-commerce platform with payment processing, inventory management, and real-time notifications."},
    ]

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{API_URL}/optimize",
            headers=HEADERS,
            json={
                "messages": messages,
                "strategy": "balanced",
                "target_model": "claude-3-5-sonnet",
                "use_memory": True,
            },
        )
        data = response.json()
        print("=== OPTIMIZE RESULT ===")
        print(f"Recommended model: {data['recommended_model']}")
        print(f"Reason: {data['model_reason']}")
        print(f"Tokens saved: {data['tokens_saved']} ({data['savings_percent']}%)")
        print(f"Cost saved: ${data['cost_saved_usd']}")
        print(f"Cache hit: {data['cache_hit']}")
        print()


async def demo_analyze():
    messages = [
        {"role": "user", "content": "Refactor the entire authentication module to use OAuth2 with PKCE flow and implement role-based access control."},
    ]

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{API_URL}/analyze",
            headers=HEADERS,
            json={"messages": messages, "target_model": "claude-3-5-sonnet"},
        )
        data = response.json()
        print("=== ANALYZE RESULT ===")
        print(f"Complexity: {data['complexity_score']}")
        print(f"Recommended strategy: {data['recommended_strategy']}")
        print(f"Estimated savings: {json.dumps(data['estimated_savings'], indent=2)}")
        print()


async def demo_memory():
    async with httpx.AsyncClient(timeout=60) as client:
        await client.post(
            f"{API_URL}/memory/save",
            headers=HEADERS,
            json={
                "content": "User prefers FastAPI with async SQLAlchemy and PostgreSQL",
                "memory_type": "preference",
                "user_id": "demo-user",
            },
        )

        response = await client.post(
            f"{API_URL}/memory/search",
            headers=HEADERS,
            json={"query": "backend framework preferences", "user_id": "demo-user"},
        )
        data = response.json()
        print("=== MEMORY SEARCH ===")
        print(f"Found {data['total_found']} memories")
        for mem in data["memories"]:
            print(f"  [{mem['memory_type']}] score={mem['relevance_score']:.2f}: {mem['content'][:80]}")
        print()


async def demo_stats():
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{API_URL}/stats", headers=HEADERS)
        data = response.json()
        print("=== STATS ===")
        print(f"Total requests: {data['total_requests']}")
        print(f"Tokens saved: {data['total_tokens_saved']}")
        print(f"Cost saved: ${data['total_cost_saved_usd']}")
        print(f"Avg compression: {data['average_compression_ratio']}")
        print()


async def main():
    print("AI Token Suppressor — Demo\n")

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            health = await client.get(f"{API_URL}/health")
            if health.status_code != 200:
                print("API not available. Run: docker compose up -d")
                return
    except httpx.ConnectError:
        print("API not available at localhost:8000")
        print("Run: docker compose up -d --build")
        return

    await demo_compress()
    await demo_analyze()
    await demo_optimize()
    await demo_memory()
    await demo_stats()
    print("Demo completed!")


if __name__ == "__main__":
    asyncio.run(main())
