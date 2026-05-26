"""Main optimization orchestrator - combines all services."""

import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.metrics import COMPRESSION_RATIO, TOKENS_SAVED
from app.schemas import CompressionStrategy, Message
from app.services.analytics_service import AnalyticsService
from app.services.cache_service import CacheService
from app.services.compression_service import CompressionService
from app.services.context_manager import ContextManager
from app.services.memory_service import MemoryService
from app.services.rag_service import RAGService
from app.services.router_service import RouterService
from app.services.token_service import TokenService

logger = get_logger(__name__)


class OptimizeService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.compression = CompressionService()
        self.context_manager = ContextManager()
        self.memory = MemoryService(db)
        self.rag = RAGService(db)
        self.router = RouterService()
        self.cache = CacheService()
        self.analytics = AnalyticsService(db)
        self.token_service = TokenService()

    async def optimize(
        self,
        messages: list[Message],
        strategy: CompressionStrategy = CompressionStrategy.BALANCED,
        target_model: str = "claude-3-5-sonnet",
        use_memory: bool = True,
        use_rag: bool = False,
        rag_collection: str = "default",
        session_id: str | None = None,
        user_id: str = "default",
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        start = time.perf_counter()
        operations: list[str] = []
        cache_hit = False

        msg_dicts = [m.model_dump() for m in messages]
        tokens_before = self.token_service.count_messages(msg_dicts)

        prompt_hash = self.cache.hash_prompt(msg_dicts)
        cached = await self.cache.get_compression(prompt_hash)
        if cached:
            cache_hit = True
            latency = (time.perf_counter() - start) * 1000
            await self.analytics.log_request(
                "optimize", tokens_before, cached["tokens_after"],
                strategy=strategy.value, model_target=target_model,
                latency_ms=latency, cache_hit=True,
            )
            return {**cached, "cache_hit": True, "latency_ms": round(latency, 2)}

        routing = self.router.route(msg_dicts, target_model=target_model, strategy=strategy.value)
        operations.append(f"routed_to:{routing['model']}")

        memory_context = ""
        memory_injected: list[str] = []
        if use_memory:
            query = msg_dicts[-1].get("content", "") if msg_dicts else ""
            if isinstance(query, str) and query:
                memory_context = await self.memory.build_context(query, user_id=user_id)
                if memory_context:
                    memory_injected.append(memory_context[:200])
                    msg_dicts.insert(0, {"role": "system", "content": memory_context})
                    operations.append("memory_injected")

        rag_context = ""
        rag_sources: list[str] = []
        if use_rag:
            query = msg_dicts[-1].get("content", "") if msg_dicts else ""
            if isinstance(query, str) and query:
                rag_context, rag_sources = await self.rag.build_rag_context(
                    query, collection_id=rag_collection
                )
                if rag_context:
                    msg_dicts.insert(0, {"role": "system", "content": rag_context})
                    operations.append("rag_injected")

        msg_dicts, ctx_ops = await self.context_manager.manage_context(
            msg_dicts, max_tokens=max_tokens
        )
        operations.extend(ctx_ops)

        compressed, comp_ops = await self.compression.compress_prompt(
            msg_dicts, strategy=strategy, max_tokens=max_tokens
        )
        operations.extend(comp_ops)

        tokens_after = self.token_service.count_messages(compressed)
        savings = self.token_service.estimate_savings(tokens_before, tokens_after)

        token_svc = TokenService(routing["model"])
        cost_saved = max(
            0,
            token_svc.estimate_cost(tokens_before, routing["model"])
            - token_svc.estimate_cost(tokens_after, routing["model"]),
        )

        latency = (time.perf_counter() - start) * 1000

        result_messages = [
            Message(role=m["role"], content=m["content"], name=m.get("name"))
            for m in compressed
        ]

        result = {
            "messages": result_messages,
            "tokens_before": tokens_before,
            "tokens_after": tokens_after,
            "tokens_saved": savings["tokens_saved"],
            "savings_percent": savings["savings_percent"],
            "recommended_model": routing["model"],
            "model_reason": routing["reason"],
            "memory_injected": memory_injected,
            "rag_context": rag_sources,
            "operations_applied": operations,
            "cache_hit": cache_hit,
            "latency_ms": round(latency, 2),
            "cost_saved_usd": round(cost_saved, 6),
        }

        await self.cache.set_compression(prompt_hash, {
            "messages": [m.model_dump() for m in result_messages],
            "tokens_after": tokens_after,
            "tokens_saved": savings["tokens_saved"],
            "savings_percent": savings["savings_percent"],
            "recommended_model": routing["model"],
            "model_reason": routing["reason"],
            "operations_applied": operations,
            "cost_saved_usd": round(cost_saved, 6),
        })

        COMPRESSION_RATIO.labels(strategy=strategy.value).observe(savings["compression_ratio"])
        TOKENS_SAVED.labels(model=routing["model"], strategy=strategy.value).inc(
            savings["tokens_saved"]
        )

        await self.analytics.log_request(
            "optimize", tokens_before, tokens_after,
            strategy=strategy.value, model_target=routing["model"],
            latency_ms=latency, cache_hit=False,
            metadata={"operations": operations},
        )

        if use_memory and msg_dicts:
            last_content = messages[-1].content if messages else ""
            if last_content:
                try:
                    await self.memory.save_memory(
                        last_content, memory_type="prompt",
                        user_id=user_id, session_id=session_id,
                    )
                except Exception as exc:
                    logger.warning("auto_save_memory_failed", error=str(exc))

        return result

    async def compress_only(
        self,
        messages: list[Message],
        strategy: CompressionStrategy = CompressionStrategy.BALANCED,
        max_tokens: int | None = None,
        preserve_system: bool = True,
    ) -> dict[str, Any]:
        start = time.perf_counter()
        msg_dicts = [m.model_dump() for m in messages]
        tokens_before = self.token_service.count_messages(msg_dicts)

        compressed, operations = await self.compression.compress_prompt(
            msg_dicts, strategy=strategy, max_tokens=max_tokens, preserve_system=preserve_system
        )

        tokens_after = self.token_service.count_messages(compressed)
        savings = self.token_service.estimate_savings(tokens_before, tokens_after)
        latency = (time.perf_counter() - start) * 1000

        result_messages = [
            Message(role=m["role"], content=m["content"], name=m.get("name"))
            for m in compressed
        ]

        await self.analytics.log_request(
            "compress", tokens_before, tokens_after,
            strategy=strategy.value, latency_ms=latency,
        )

        return {
            "messages": result_messages,
            "tokens_before": tokens_before,
            "tokens_after": tokens_after,
            "tokens_saved": savings["tokens_saved"],
            "savings_percent": savings["savings_percent"],
            "compression_ratio": savings["compression_ratio"],
            "strategy": strategy,
            "operations_applied": operations,
            "latency_ms": round(latency, 2),
        }
