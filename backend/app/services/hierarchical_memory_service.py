"""Multi-layer hierarchical memory: L1 Redis, L2 pgvector, L3 cold summaries."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.services.cache_service import CacheService
from app.services.decay_service import DecayService
from app.services.memory_service import MemoryService
from app.services.ollama_service import OllamaService

logger = get_logger(__name__)

L1_PREFIX = "ats:mem:l1:"
L3_PREFIX = "ats:mem:l3:"


@dataclass
class MemoryRecall:
    content: str
    summary: str | None
    tier: str
    score: float
    source: str


class HierarchicalMemoryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.l2 = MemoryService(db)
        self.cache = CacheService()
        self.decay = DecayService()
        self.ollama = OllamaService()

    async def save(
        self,
        content: str,
        user_id: str = "default",
        session_id: str | None = None,
        memory_type: str = "context",
        metadata: dict | None = None,
    ) -> MemoryRecall:
        redis = await self.cache._redis()
        l1_key = f"{L1_PREFIX}{user_id}:{hash(content) % 10**8}"
        l1_data = {
            "content": content,
            "memory_type": memory_type,
            "created_at": datetime.now(UTC).isoformat(),
            "metadata": metadata or {},
        }
        await redis.setex(l1_key, 3600, json.dumps(l1_data))

        memory = await self.l2.save_memory(
            content, memory_type=memory_type,
            user_id=user_id, session_id=session_id, metadata=metadata,
        )

        try:
            cold_summary = await self.ollama.summarize(content, max_words=50)
            l3_key = f"{L3_PREFIX}{user_id}:{memory.id}"
            await redis.setex(l3_key, 86400 * 30, cold_summary)
        except Exception:
            cold_summary = content[:100]

        return MemoryRecall(
            content=content,
            summary=cold_summary,
            tier="L1+L2+L3",
            score=1.0,
            source="hierarchical_save",
        )

    async def recall(
        self,
        query: str,
        user_id: str = "default",
        top_k: int = 5,
    ) -> list[MemoryRecall]:
        recalls: list[MemoryRecall] = []

        redis = await self.cache._redis()
        async for key in redis.scan_iter(match=f"{L1_PREFIX}{user_id}:*", count=50):
            data = await redis.get(key)
            if data:
                parsed = json.loads(data)
                if query.lower() in parsed.get("content", "").lower():
                    recalls.append(MemoryRecall(
                        content=parsed["content"],
                        summary=None,
                        tier="L1",
                        score=0.9,
                        source="redis_hot",
                    ))

        l2_results = await self.l2.semantic_search(query, user_id=user_id, top_k=top_k)
        for memory, score in l2_results:
            decayed = self.decay.decay_score(
                memory.created_at, score, memory.access_count,
                memory.memory_type.value,
            )
            recalls.append(MemoryRecall(
                content=memory.content,
                summary=memory.summary,
                tier="L2",
                score=decayed,
                source=str(memory.id),
            ))

        async for key in redis.scan_iter(match=f"{L3_PREFIX}{user_id}:*", count=20):
            summary = await redis.get(key)
            if summary and any(w in summary.lower() for w in query.lower().split()):
                recalls.append(MemoryRecall(
                    content=summary,
                    summary=summary,
                    tier="L3",
                    score=0.4,
                    source="cold_summary",
                ))

        recalls.sort(key=lambda r: r.score, reverse=True)
        seen: set[str] = set()
        unique: list[MemoryRecall] = []
        for r in recalls:
            fp = r.content[:100]
            if fp not in seen:
                seen.add(fp)
                unique.append(r)
        return unique[:top_k]

    async def build_context(self, query: str, user_id: str = "default", top_k: int = 3) -> str:
        recalls = await self.recall(query, user_id=user_id, top_k=top_k)
        if not recalls:
            return ""
        parts = ["[Hierarchical memory recall]"]
        for r in recalls:
            text = r.summary or r.content[:200]
            parts.append(f"- [{r.tier} score={r.score:.2f}] {text}")
        return "\n".join(parts)

    async def promote(self, memory_id: str, user_id: str) -> None:
        redis = await self.cache._redis()
        l1_key = f"{L1_PREFIX}{user_id}:promoted:{memory_id}"
        await redis.setex(l1_key, 7200, json.dumps({"promoted_at": datetime.now(UTC).isoformat()}))

    async def consolidate_cold(self, user_id: str) -> int:
        count = 0
        redis = await self.cache._redis()
        async for key in redis.scan_iter(match=f"{L3_PREFIX}{user_id}:*", count=100):
            ttl = await redis.ttl(key)
            if ttl > 0 and ttl < 86400:
                count += 1
        return count
