"""Semantic memory service with pgvector."""

import uuid
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.metrics import MEMORY_RECALLS
from app.models import MemoryTypeEnum, SemanticMemory
from app.services.cache_service import CacheService
from app.services.ollama_service import OllamaService
from app.utils.helpers import cosine_similarity

logger = get_logger(__name__)


class MemoryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.ollama = OllamaService()
        self.cache = CacheService()

    async def save_memory(
        self,
        content: str,
        memory_type: str = "context",
        user_id: str = "default",
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SemanticMemory:
        summary: str | None = None
        try:
            summary = await self.ollama.summarize(content, max_words=80)
        except Exception:
            summary = content[:200]

        embedding: list[float] | None = None
        cached = await self.cache.get_embedding(content)
        if cached:
            embedding = cached
        else:
            try:
                embedding = await self.ollama.create_embedding(content)
                await self.cache.set_embedding(content, embedding)
            except Exception as exc:
                logger.warning("embedding_failed_on_save", error=str(exc))

        try:
            mem_type = MemoryTypeEnum(memory_type)
        except ValueError:
            mem_type = MemoryTypeEnum.CONTEXT

        memory = SemanticMemory(
            id=uuid.uuid4(),
            user_id=user_id,
            session_id=session_id,
            memory_type=mem_type,
            content=content,
            summary=summary,
            embedding=embedding,
            metadata_=metadata or {},
        )
        self.db.add(memory)
        await self.db.flush()
        return memory

    async def semantic_search(
        self,
        query: str,
        user_id: str = "default",
        top_k: int = 5,
        memory_types: list[str] | None = None,
        min_score: float = 0.5,
    ) -> list[tuple[SemanticMemory, float]]:
        query_embedding: list[float] | None = None
        cached = await self.cache.get_embedding(query)
        if cached:
            query_embedding = cached
        else:
            try:
                query_embedding = await self.ollama.create_embedding(query)
                await self.cache.set_embedding(query, query_embedding)
            except Exception as exc:
                logger.warning("query_embedding_failed", error=str(exc))
                return await self._fallback_text_search(query, user_id, top_k, memory_types)

        if query_embedding:
            try:
                return await self._vector_search(
                    query_embedding, user_id, top_k, memory_types, min_score
                )
            except Exception as exc:
                logger.warning("vector_search_failed", error=str(exc))

        return await self._fallback_text_search(query, user_id, top_k, memory_types)

    async def _vector_search(
        self,
        embedding: list[float],
        user_id: str,
        top_k: int,
        memory_types: list[str] | None,
        min_score: float,
    ) -> list[tuple[SemanticMemory, float]]:
        embedding_str = f"[{','.join(str(x) for x in embedding)}]"

        type_filter = ""
        if memory_types:
            types_str = ",".join(f"'{t}'" for t in memory_types)
            type_filter = f"AND memory_type::text IN ({types_str})"

        sql = text(f"""
            SELECT id, content, summary, memory_type, metadata, relevance_score,
                   access_count, created_at, updated_at, user_id, session_id,
                   1 - (embedding <=> :embedding::vector) AS similarity
            FROM semantic_memories
            WHERE user_id = :user_id
              AND embedding IS NOT NULL
              {type_filter}
            ORDER BY embedding <=> :embedding::vector
            LIMIT :top_k
        """)

        result = await self.db.execute(
            sql, {"embedding": embedding_str, "user_id": user_id, "top_k": top_k * 2}
        )
        rows = result.fetchall()

        memories_with_scores: list[tuple[SemanticMemory, float]] = []
        for row in rows:
            similarity = float(row.similarity) if row.similarity else 0.0
            if similarity < min_score:
                continue
            memory = SemanticMemory(
                id=row.id,
                content=row.content,
                summary=row.summary,
                memory_type=row.memory_type,
                metadata_=row.metadata or {},
                relevance_score=row.relevance_score,
                access_count=row.access_count,
                created_at=row.created_at,
                updated_at=row.updated_at,
                user_id=row.user_id,
                session_id=row.session_id,
            )
            memories_with_scores.append((memory, similarity))

        MEMORY_RECALLS.inc(len(memories_with_scores))
        return memories_with_scores[:top_k]

    async def _fallback_text_search(
        self,
        query: str,
        user_id: str,
        top_k: int,
        memory_types: list[str] | None,
    ) -> list[tuple[SemanticMemory, float]]:
        stmt = select(SemanticMemory).where(SemanticMemory.user_id == user_id)
        if memory_types:
            stmt = stmt.where(
                SemanticMemory.memory_type.in_([MemoryTypeEnum(t) for t in memory_types])
            )
        stmt = stmt.order_by(SemanticMemory.created_at.desc()).limit(top_k * 3)
        result = await self.db.execute(stmt)
        memories = result.scalars().all()

        query_lower = query.lower()
        scored: list[tuple[SemanticMemory, float]] = []
        for mem in memories:
            content_lower = mem.content.lower()
            words = query_lower.split()
            hits = sum(1 for w in words if w in content_lower)
            score = hits / max(len(words), 1)
            if score > 0:
                scored.append((mem, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    async def retrieve_relevant_memories(
        self,
        query: str,
        user_id: str = "default",
        session_id: str | None = None,
        top_k: int = 5,
    ) -> list[SemanticMemory]:
        results = await self.semantic_search(query, user_id=user_id, top_k=top_k)
        memory_ids = [mem.id for mem, _ in results]
        if memory_ids:
            await self.db.execute(
                update(SemanticMemory)
                .where(SemanticMemory.id.in_(memory_ids))
                .values(access_count=SemanticMemory.access_count + 1)
            )
        return [mem for mem, _ in results]

    async def build_context(
        self,
        query: str,
        user_id: str = "default",
        top_k: int = 3,
    ) -> str:
        memories = await self.retrieve_relevant_memories(query, user_id=user_id, top_k=top_k)
        if not memories:
            return ""

        parts = ["[Relevant memories from previous interactions]"]
        for mem in memories:
            text = mem.summary or mem.content[:300]
            parts.append(f"- ({mem.memory_type.value}): {text}")

        return "\n".join(parts)
