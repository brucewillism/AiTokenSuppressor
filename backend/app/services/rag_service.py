"""RAG pipeline with intelligent chunking and semantic retrieval."""

import re
import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import RAGDocument
from app.services.cache_service import CacheService
from app.services.chunking_service import ChunkingService
from app.services.ollama_service import OllamaService

logger = get_logger(__name__)
settings = get_settings()


class RAGService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.ollama = OllamaService()
        self.cache = CacheService()
        self.chunking = ChunkingService()
        self.chunk_size = settings.rag_chunk_size
        self.chunk_overlap = settings.rag_chunk_overlap
        self.top_k = settings.rag_top_k

    def intelligent_chunk(self, content: str, language: str | None = None, use_ast: bool = True) -> list[str]:
        chunks = self.chunking.chunk(content, language=language, use_ast=use_ast)
        return [c.content for c in chunks]

    def _split_text(self, text: str, size: int) -> list[str]:
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = start + size
            if end < len(text):
                break_point = text.rfind("\n", start, end)
                if break_point > start:
                    end = break_point
            chunks.append(text[start:end].strip())
            start = end - self.chunk_overlap if end < len(text) else end
        return chunks

    async def ingest(
        self,
        content: str,
        collection_id: str = "default",
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
        chunk_by_ast: bool = True,
        language: str | None = None,
    ) -> int:
        chunks = self.intelligent_chunk(content, language=language, use_ast=chunk_by_ast)
        created = 0

        for idx, chunk_text in enumerate(chunks):
            embedding: list[float] | None = None
            try:
                cached = await self.cache.get_embedding(chunk_text)
                if cached:
                    embedding = cached
                else:
                    embedding = await self.ollama.create_embedding(chunk_text)
                    await self.cache.set_embedding(chunk_text, embedding)
            except Exception as exc:
                logger.warning("rag_embedding_failed", chunk_index=idx, error=str(exc))

            doc = RAGDocument(
                id=uuid.uuid4(),
                collection_id=collection_id,
                source=source,
                content=chunk_text,
                chunk_index=idx,
                embedding=embedding,
                metadata_=metadata or {},
            )
            self.db.add(doc)
            created += 1

        await self.db.flush()
        return created

    async def query(
        self,
        query: str,
        collection_id: str = "default",
        top_k: int | None = None,
        rerank: bool = True,
    ) -> list[tuple[RAGDocument, float]]:
        k = top_k or self.top_k

        query_embedding: list[float] | None = None
        try:
            cached = await self.cache.get_embedding(query)
            if cached:
                query_embedding = cached
            else:
                query_embedding = await self.ollama.create_embedding(query)
                await self.cache.set_embedding(query, query_embedding)
        except Exception as exc:
            logger.warning("rag_query_embedding_failed", error=str(exc))
            return await self._fallback_search(query, collection_id, k)

        if query_embedding:
            try:
                results = await self._vector_query(query_embedding, collection_id, k * 2)
                if rerank and results:
                    results = await self._rerank(query, results)
                return results[:k]
            except Exception as exc:
                logger.warning("rag_vector_query_failed", error=str(exc))

        return await self._fallback_search(query, collection_id, k)

    async def _vector_query(
        self,
        embedding: list[float],
        collection_id: str,
        top_k: int,
    ) -> list[tuple[RAGDocument, float]]:
        embedding_str = f"[{','.join(str(x) for x in embedding)}]"

        sql = text("""
            SELECT id, collection_id, source, content, chunk_index, metadata, created_at,
                   1 - (embedding <=> :embedding::vector) AS similarity
            FROM rag_documents
            WHERE collection_id = :collection_id
              AND embedding IS NOT NULL
            ORDER BY embedding <=> :embedding::vector
            LIMIT :top_k
        """)

        result = await self.db.execute(
            sql,
            {"embedding": embedding_str, "collection_id": collection_id, "top_k": top_k},
        )
        rows = result.fetchall()

        docs: list[tuple[RAGDocument, float]] = []
        for row in rows:
            doc = RAGDocument(
                id=row.id,
                collection_id=row.collection_id,
                source=row.source,
                content=row.content,
                chunk_index=row.chunk_index,
                metadata_=row.metadata or {},
                created_at=row.created_at,
            )
            docs.append((doc, float(row.similarity or 0.0)))
        return docs

    async def _fallback_search(
        self, query: str, collection_id: str, top_k: int
    ) -> list[tuple[RAGDocument, float]]:
        stmt = (
            select(RAGDocument)
            .where(RAGDocument.collection_id == collection_id)
            .order_by(RAGDocument.created_at.desc())
            .limit(top_k * 3)
        )
        result = await self.db.execute(stmt)
        docs = result.scalars().all()

        query_words = set(query.lower().split())
        scored: list[tuple[RAGDocument, float]] = []
        for doc in docs:
            content_words = set(doc.content.lower().split())
            overlap = len(query_words & content_words)
            score = overlap / max(len(query_words), 1)
            if score > 0:
                scored.append((doc, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    async def _rerank(
        self, query: str, results: list[tuple[RAGDocument, float]]
    ) -> list[tuple[RAGDocument, float]]:
        reranked: list[tuple[RAGDocument, float]] = []
        for doc, vector_score in results:
            try:
                relevance = await self.ollama.classify_relevance(doc.content[:1000], query)
                combined = vector_score * 0.6 + relevance * 0.4
                reranked.append((doc, combined))
            except Exception:
                reranked.append((doc, vector_score))

        reranked.sort(key=lambda x: x[1], reverse=True)
        return reranked

    async def build_rag_context(
        self,
        query: str,
        collection_id: str = "default",
        top_k: int = 3,
        adaptive: bool = False,
        max_context_tokens: int | None = None,
    ) -> tuple[str, list[str]]:
        effective_top_k = top_k
        adaptive_params: dict[str, Any] = {}

        if adaptive:
            query_len = len(query.split())
            if query_len < 10:
                effective_top_k = min(top_k, 2)
                adaptive_params["mode"] = "minimal"
            elif query_len > 50:
                effective_top_k = min(top_k + 2, 10)
                adaptive_params["mode"] = "expanded"
            else:
                adaptive_params["mode"] = "balanced"

        results = await self.query(query, collection_id=collection_id, top_k=effective_top_k)
        if not results:
            return "", []

        parts = ["[Retrieved context]"]
        sources: list[str] = []
        token_budget = max_context_tokens or 4000
        tokens_used = 0

        for doc, score in results:
            chunk_tokens = len(doc.content) // 4
            if tokens_used + chunk_tokens > token_budget:
                adaptive_params["truncated"] = True
                break
            meta = doc.metadata_ or {}
            symbol = meta.get("symbol", "")
            header = f"[Source: {doc.source or 'unknown'}, score: {score:.2f}"
            if symbol:
                header += f", symbol: {symbol}"
            header += "]"
            parts.append(f"{header}\n{doc.content}")
            tokens_used += chunk_tokens
            if doc.source:
                sources.append(doc.source)

        return "\n\n".join(parts), sources
