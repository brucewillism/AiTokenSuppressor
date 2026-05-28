"""Main optimization orchestrator - enterprise semantic pipeline."""

import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.metrics import COMPRESSION_RATIO, TOKENS_SAVED
from app.schemas import CompressionStrategy, Message, MessageRole
from app.services.analytics_service import AnalyticsService
from app.services.cache_service import CacheService
from app.services.compression_service import CompressionService
from app.services.content_detection_service import ContentDetectionService
from app.services.context_graph_service import ContextGraphService
from app.services.context_manager import ContextManager
from app.services.cost_optimizer_service import CostOptimizerService
from app.services.fingerprint_service import FingerprintService
from app.services.hierarchical_memory_service import HierarchicalMemoryService
from app.services.memory_service import MemoryService
from app.services.rag_service import RAGService
from app.services.router_service import RouterService
from app.services.semantic_loss_service import SemanticLossService
from app.services.token_heatmap_service import TokenHeatmapService
from app.services.token_service import TokenService

logger = get_logger(__name__)


def _dict_to_message(data: dict) -> Message:
    role = data.get("role", "user")
    if not isinstance(role, MessageRole):
        try:
            role = MessageRole(str(role))
        except ValueError:
            role = MessageRole.USER
    content = data.get("content", "")
    if not isinstance(content, str):
        content = str(content)
    return Message(role=role, content=content, name=data.get("name"))


class OptimizeService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.compression = CompressionService()
        self.context_manager = ContextManager()
        self.memory = MemoryService(db)
        self.hierarchical_memory = HierarchicalMemoryService(db)
        self.rag = RAGService(db)
        self.router = RouterService()
        self.cache = CacheService()
        self.analytics = AnalyticsService(db)
        self.token_service = TokenService()
        self.fingerprint = FingerprintService()
        self.semantic_loss = SemanticLossService()
        self.cost_optimizer = CostOptimizerService()
        self.content_detector = ContentDetectionService()
        self.context_graph = ContextGraphService()
        self.heatmap = TokenHeatmapService()

    async def optimize(
        self,
        messages: list[Message],
        strategy: CompressionStrategy = CompressionStrategy.BALANCED,
        target_model: str = "claude-3-5-sonnet",
        provider: str = "anthropic",
        use_memory: bool = True,
        use_rag: bool = False,
        use_hierarchical_memory: bool = True,
        use_semantic_cache: bool = True,
        rag_collection: str = "default",
        session_id: str | None = None,
        user_id: str = "default",
        max_tokens: int | None = None,
        check_semantic_loss: bool = True,
        use_ollama: bool | None = None,
        cost_budget_usd: float | None = None,
    ) -> dict[str, Any]:
        start = time.perf_counter()
        operations: list[str] = []
        cache_hit = False
        semantic_cache_hit = False

        msg_dicts = [m.model_dump() for m in messages]
        tokens_before = self.token_service.count_messages(msg_dicts)

        heatmap_data = self.heatmap.generate(msg_dicts, target_model)
        content_types = {
            str(s["index"]): s["content_type"] for s in heatmap_data["segments"]
        }

        fp = self.fingerprint.fingerprint_messages(msg_dicts)
        prompt_hash = self.cache.hash_prompt(msg_dicts)

        if use_semantic_cache:
            similar = self.fingerprint.find_similar(
                " ".join(str(m.get("content", "")) for m in msg_dicts)
            )
            if similar and similar[0][1] >= 0.92:
                cached = await self.cache.get_compression(similar[0][0])
                if cached:
                    semantic_cache_hit = True
                    cache_hit = True
                    latency = (time.perf_counter() - start) * 1000
                    await self.analytics.log_request(
                        "optimize", tokens_before, cached["tokens_after"],
                        strategy=strategy.value, model_target=target_model,
                        latency_ms=latency, cache_hit=True,
                        metadata={"semantic_cache": True, "similarity": similar[0][1]},
                    )
                    return self._build_response(
                        cached, messages, tokens_before, cache_hit=True,
                        latency=latency, heatmap=heatmap_data, content_types=content_types,
                        semantic_loss_score=cached.get("semantic_loss_score"),
                    )

        cached = await self.cache.get_compression(prompt_hash)
        if cached:
            cache_hit = True
            latency = (time.perf_counter() - start) * 1000
            await self.analytics.log_request(
                "optimize", tokens_before, cached["tokens_after"],
                strategy=strategy.value, model_target=target_model,
                latency_ms=latency, cache_hit=True,
            )
            return self._build_response(
                cached, messages, tokens_before, cache_hit=True,
                latency=latency, heatmap=heatmap_data, content_types=content_types,
                semantic_loss_score=cached.get("semantic_loss_score"),
            )

        complexity = self.router.analyze_complexity(msg_dicts)
        cost_decision = self.cost_optimizer.decide(
            msg_dicts, target_model, provider, cost_budget_usd, complexity,
        )
        operations.append(f"cost_decision:{cost_decision.reason}")

        routing = self.router.route(
            msg_dicts, target_model=target_model, strategy=strategy.value,
            provider=provider, context_tokens=tokens_before,
        )
        operations.append(f"routed_to:{routing['model']}")

        graph_context: list[str] = []
        query = msg_dicts[-1].get("content", "") if msg_dicts else ""
        if isinstance(query, str) and query:
            self.context_graph.ingest(user_id, query)
            graph_ctx = self.context_graph.build_context(user_id, query)
            if graph_ctx:
                graph_context.append(graph_ctx[:200])
                msg_dicts.insert(0, {"role": "system", "content": graph_ctx})
                operations.append("context_graph_injected")

        memory_injected: list[str] = []
        if use_memory:
            if use_hierarchical_memory and isinstance(query, str) and query:
                mem_ctx = await self.hierarchical_memory.build_context(query, user_id=user_id)
            elif isinstance(query, str) and query:
                mem_ctx = await self.memory.build_context(query, user_id=user_id)
            else:
                mem_ctx = ""
            if mem_ctx:
                memory_injected.append(mem_ctx[:200])
                msg_dicts.insert(0, {"role": "system", "content": mem_ctx})
                operations.append("memory_injected")

        rag_sources: list[str] = []
        if use_rag and isinstance(query, str) and query:
            rag_context, rag_sources = await self.rag.build_rag_context(
                query, collection_id=rag_collection, adaptive=True,
                max_context_tokens=max_tokens,
            )
            if rag_context:
                msg_dicts.insert(0, {"role": "system", "content": rag_context})
                operations.append("adaptive_rag_injected")

        if cost_decision.max_tokens_budget and not max_tokens:
            max_tokens = cost_decision.max_tokens_budget

        msg_dicts, ctx_ops = await self.context_manager.manage_context(
            msg_dicts, max_tokens=max_tokens,
        )
        operations.extend(ctx_ops)

        effective_strategy = strategy
        if cost_decision.should_compress and strategy == CompressionStrategy.BALANCED:
            if complexity < 0.4:
                effective_strategy = CompressionStrategy.AGGRESSIVE
                operations.append("adaptive_strategy:aggressive")

        compressed, comp_ops = await self.compression.compress_prompt(
            msg_dicts,
            strategy=effective_strategy,
            max_tokens=max_tokens,
            use_ollama=use_ollama,
        )
        operations.extend(comp_ops)

        semantic_loss_score: float | None = None
        quality_preserved = True
        if check_semantic_loss:
            loss_report = await self.semantic_loss.measure(msg_dicts, compressed)
            semantic_loss_score = loss_report.loss_score
            quality_preserved = loss_report.quality_preserved
            operations.append(f"semantic_loss:{loss_report.loss_score:.3f}")
            if not self.semantic_loss.is_acceptable(loss_report):
                operations.append("semantic_loss_high:quality_restored")
                compressed, _ = self.compression.quality_guard.merge_with_compressed(
                    msg_dicts, compressed
                )

        tokens_after = self.token_service.count_messages(compressed)
        savings = self.token_service.estimate_savings(tokens_before, tokens_after)

        token_svc = TokenService(routing["model"])
        cost_saved = self.cost_optimizer.estimate_savings_usd(
            tokens_before, tokens_after, routing["model"],
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
            "semantic_loss_score": semantic_loss_score,
            "content_types": content_types,
            "token_heatmap": heatmap_data["segments"],
            "routing_details": routing,
            "graph_context": graph_context,
            "quality_preserved": quality_preserved,
        }

        cache_payload = {
            "messages": [m.model_dump() for m in result_messages],
            "tokens_after": tokens_after,
            "tokens_saved": savings["tokens_saved"],
            "savings_percent": savings["savings_percent"],
            "recommended_model": routing["model"],
            "model_reason": routing["reason"],
            "operations_applied": operations,
            "cost_saved_usd": round(cost_saved, 6),
            "semantic_loss_score": semantic_loss_score,
        }
        await self.cache.set_compression(prompt_hash, cache_payload)
        if use_semantic_cache:
            try:
                from app.services.ollama_service import OllamaService
                emb = await OllamaService().create_embedding(query[:2000] if isinstance(query, str) else "")
                await self.cache.cache_with_embedding(
                    fp, cache_payload, emb,
                )
            except Exception:
                pass

        COMPRESSION_RATIO.labels(strategy=strategy.value).observe(savings["compression_ratio"])
        TOKENS_SAVED.labels(model=routing["model"], strategy=strategy.value).inc(
            savings["tokens_saved"]
        )

        await self.analytics.log_request(
            "optimize", tokens_before, tokens_after,
            strategy=strategy.value, model_target=routing["model"],
            latency_ms=latency, cache_hit=cache_hit,
            metadata={
                "operations": operations,
                "semantic_loss": semantic_loss_score,
                "semantic_cache": semantic_cache_hit,
            },
        )

        if use_memory and messages:
            last_content = messages[-1].content
            try:
                if use_hierarchical_memory:
                    await self.hierarchical_memory.save(
                        last_content, user_id=user_id, session_id=session_id,
                    )
                else:
                    await self.memory.save_memory(
                        last_content, memory_type="prompt",
                        user_id=user_id, session_id=session_id,
                    )
                entities = self.context_graph.extract_entities(last_content)
                if entities:
                    self.context_graph.ingest(
                        user_id, last_content,
                        entities=[e.label for e in entities],
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
        target_model: str = "claude-3-5-sonnet",
        check_semantic_loss: bool = True,
        use_ollama: bool | None = None,
    ) -> dict[str, Any]:
        start = time.perf_counter()
        msg_dicts = [m.model_dump() for m in messages]
        tokens_before = self.token_service.count_messages(msg_dicts)
        heatmap_data = self.heatmap.generate(msg_dicts, target_model)
        content_types = {str(s["index"]): s["content_type"] for s in heatmap_data["segments"]}

        compressed, operations = await self.compression.compress_prompt(
            msg_dicts,
            strategy=strategy,
            max_tokens=max_tokens,
            preserve_system=preserve_system,
            use_ollama=use_ollama,
        )

        semantic_loss_score: float | None = None
        quality_preserved = True
        if check_semantic_loss:
            loss_report = await self.semantic_loss.measure(msg_dicts, compressed)
            semantic_loss_score = loss_report.loss_score
            quality_preserved = loss_report.quality_preserved

        tokens_after = self.token_service.count_messages(compressed)
        savings = self.token_service.estimate_savings(tokens_before, tokens_after)
        latency = (time.perf_counter() - start) * 1000

        result_messages = [_dict_to_message(m) for m in compressed]

        try:
            await self.analytics.log_request(
                "compress",
                tokens_before,
                tokens_after,
                strategy=strategy.value,
                model_target=target_model,
                latency_ms=latency,
                metadata={"semantic_loss": semantic_loss_score},
            )
        except Exception as exc:
            logger.warning("compress_analytics_skipped", error=str(exc))

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
            "semantic_loss_score": semantic_loss_score,
            "content_types": content_types,
            "token_heatmap": heatmap_data["segments"],
            "quality_preserved": quality_preserved,
        }

    def _build_response(
        self, cached: dict, messages: list[Message], tokens_before: int,
        cache_hit: bool, latency: float, heatmap: dict,
        content_types: dict, semantic_loss_score: float | None,
    ) -> dict[str, Any]:
        result_messages = [
            Message(**m) for m in cached.get("messages", [])
        ]
        return {
            "messages": result_messages,
            "tokens_before": tokens_before,
            "tokens_after": cached.get("tokens_after", 0),
            "tokens_saved": cached.get("tokens_saved", 0),
            "savings_percent": cached.get("savings_percent", 0),
            "recommended_model": cached.get("recommended_model", ""),
            "model_reason": cached.get("model_reason", "cache hit"),
            "memory_injected": [],
            "rag_context": [],
            "operations_applied": cached.get("operations_applied", ["cache_hit"]),
            "cache_hit": cache_hit,
            "latency_ms": round(latency, 2),
            "cost_saved_usd": cached.get("cost_saved_usd", 0),
            "semantic_loss_score": semantic_loss_score,
            "content_types": content_types,
            "token_heatmap": heatmap.get("segments", []),
            "routing_details": {},
            "graph_context": [],
            "quality_preserved": True,
        }
