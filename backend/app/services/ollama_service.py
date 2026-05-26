"""Ollama local LLM integration with connection pooling and keep_alive."""

import asyncio
import json
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.exceptions import OllamaError
from app.core.logging import get_logger
from app.core.metrics import OLLAMA_REQUESTS

logger = get_logger(__name__)
settings = get_settings()

_client: httpx.AsyncClient | None = None
_warmup_done: bool = False


async def get_ollama_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=settings.ollama_timeout,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _client


class OllamaService:
    KEEP_ALIVE = "10m"

    def __init__(self) -> None:
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model = settings.ollama_model
        self.embed_model = settings.ollama_embed_model
        self.timeout = settings.ollama_timeout

    async def warmup(self) -> None:
        global _warmup_done
        if _warmup_done:
            return
        try:
            client = await get_ollama_client()
            await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": "ping",
                    "stream": False,
                    "keep_alive": self.KEEP_ALIVE,
                    "options": {"num_predict": 1},
                },
            )
            _warmup_done = True
            logger.info("ollama_warmup_complete", model=self.model)
        except httpx.HTTPError as exc:
            logger.warning("ollama_warmup_failed", error=str(exc))

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def _request(
        self, endpoint: str, payload: dict[str, Any], operation: str
    ) -> dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        payload.setdefault("keep_alive", self.KEEP_ALIVE)
        try:
            client = await get_ollama_client()
            response = await client.post(url, json=payload)
            response.raise_for_status()
            OLLAMA_REQUESTS.labels(operation=operation, status="success").inc()
            return response.json()
        except httpx.HTTPError as exc:
            OLLAMA_REQUESTS.labels(operation=operation, status="error").inc()
            logger.error("ollama_request_failed", operation=operation, error=str(exc))
            raise OllamaError(f"Ollama request failed: {exc}") from exc

    async def health_check(self) -> dict[str, Any]:
        try:
            client = await get_ollama_client()
            start = __import__("time").perf_counter()
            response = await client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            latency = (__import__("time").perf_counter() - start) * 1000
            data = response.json()
            return {
                "status": "healthy",
                "latency_ms": round(latency, 2),
                "models": [m["name"] for m in data.get("models", [])],
            }
        except httpx.HTTPError as exc:
            return {"status": "unhealthy", "error": str(exc)}

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
        model: str | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model or self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if system:
            payload["system"] = system
        result = await self._request("/api/generate", payload, "generate")
        return result.get("response", "")

    async def summarize(self, text: str, max_words: int = 150) -> str:
        prompt = (
            f"Summarize the following text concisely in at most {max_words} words. "
            f"Preserve key facts, decisions, and technical details. "
            f"Output only the summary, no preamble.\n\n{text[:8000]}"
        )
        return await self.generate(
            prompt,
            system="You are a precise summarization assistant. Be concise and factual.",
            temperature=0.2,
        )

    async def compress(self, text: str, target_ratio: float = 0.5) -> str:
        prompt = (
            f"Compress the following text to approximately {int(target_ratio * 100)}% "
            f"of its original length while preserving all critical information, "
            f"code snippets, and technical details. Remove redundancy and verbosity.\n\n{text[:8000]}"
        )
        return await self.generate(
            prompt,
            system="You are a text compression specialist. Output only the compressed text.",
            temperature=0.1,
        )

    async def classify_relevance(self, text: str, context: str) -> float:
        prompt = (
            f"Rate the relevance of the following text to the given context "
            f"on a scale from 0.0 to 1.0. Output ONLY a decimal number.\n\n"
            f"Context: {context[:2000]}\n\nText: {text[:2000]}"
        )
        response = await self.generate(prompt, temperature=0.0, max_tokens=10)
        try:
            score = float(response.strip().split()[0])
            return max(0.0, min(1.0, score))
        except (ValueError, IndexError):
            return 0.5

    async def create_embedding(self, text: str) -> list[float]:
        payload = {"model": self.embed_model, "prompt": text[:8000]}
        result = await self._request("/api/embeddings", payload, "embedding")
        embedding = result.get("embedding", [])
        if not embedding:
            raise OllamaError("Empty embedding returned from Ollama")
        return embedding

    async def create_embeddings_batch(self, texts: list[str], batch_size: int = 5) -> list[list[float]]:
        embeddings: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            tasks = [self.create_embedding(t) for t in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, list):
                    embeddings.append(r)
                else:
                    embeddings.append([])
        return embeddings

    async def detect_redundancy(self, messages: list[str]) -> list[int]:
        if len(messages) <= 1:
            return []
        prompt = (
            "Analyze these messages and return a JSON array of indices (0-based) "
            "of messages that are redundant or duplicate. "
            f"Messages:\n{json.dumps(messages[:20], ensure_ascii=False)}"
        )
        response = await self.generate(prompt, temperature=0.0, max_tokens=256)
        try:
            start = response.index("[")
            end = response.rindex("]") + 1
            indices = json.loads(response[start:end])
            return [int(i) for i in indices if isinstance(i, (int, float))]
        except (ValueError, json.JSONDecodeError):
            return []
