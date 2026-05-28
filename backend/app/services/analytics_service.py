"""Analytics and telemetry service."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import RequestLog
from app.services.cache_service import CacheService
from app.services.token_service import TokenService

logger = get_logger(__name__)


class AnalyticsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.cache = CacheService()
        self.token_service = TokenService()

    async def log_request(
        self,
        endpoint: str,
        tokens_before: int,
        tokens_after: int,
        strategy: str = "balanced",
        model_target: str | None = None,
        latency_ms: float = 0.0,
        cache_hit: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> RequestLog:
        tokens_saved = max(0, tokens_before - tokens_after)
        ratio = tokens_after / tokens_before if tokens_before > 0 else 1.0
        cost_saved = 0.0
        if model_target and tokens_saved > 0:
            cost_before = self.token_service.estimate_cost(tokens_before, model_target)
            cost_after = self.token_service.estimate_cost(tokens_after, model_target)
            cost_saved = max(0, cost_before - cost_after)

        log = RequestLog(
            id=uuid.uuid4(),
            endpoint=endpoint,
            strategy=strategy,
            model_target=model_target,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            tokens_saved=tokens_saved,
            compression_ratio=round(ratio, 4),
            cost_saved_usd=round(cost_saved, 6),
            latency_ms=round(latency_ms, 2),
            cache_hit=cache_hit,
            metadata_=metadata or {},
        )
        try:
            self.db.add(log)
            await self.db.flush()
        except Exception as exc:
            logger.warning("analytics_log_db_failed", error=str(exc))
            try:
                await self.db.rollback()
            except Exception:
                pass
            return None

        try:
            await self.cache.increment_stat("total_requests")
            await self.cache.increment_stat("total_tokens_saved", tokens_saved)
        except Exception as exc:
            logger.warning("analytics_log_redis_failed", error=str(exc))

        return log

    async def get_stats(self, days: int = 7) -> dict[str, Any]:
        since = datetime.now(UTC) - timedelta(days=days)

        total_stmt = select(func.count(RequestLog.id)).where(RequestLog.created_at >= since)
        total_result = await self.db.execute(total_stmt)
        total_requests = total_result.scalar() or 0

        saved_stmt = select(func.sum(RequestLog.tokens_saved)).where(
            RequestLog.created_at >= since
        )
        saved_result = await self.db.execute(saved_stmt)
        total_tokens_saved = saved_result.scalar() or 0

        cost_stmt = select(func.sum(RequestLog.cost_saved_usd)).where(
            RequestLog.created_at >= since
        )
        cost_result = await self.db.execute(cost_stmt)
        total_cost_saved = cost_result.scalar() or 0.0

        ratio_stmt = select(func.avg(RequestLog.compression_ratio)).where(
            RequestLog.created_at >= since
        )
        ratio_result = await self.db.execute(ratio_stmt)
        avg_ratio = ratio_result.scalar() or 0.0

        latency_stmt = select(func.avg(RequestLog.latency_ms)).where(
            RequestLog.created_at >= since
        )
        latency_result = await self.db.execute(latency_stmt)
        avg_latency = latency_result.scalar() or 0.0

        cache_stmt = select(func.count(RequestLog.id)).where(
            RequestLog.created_at >= since, RequestLog.cache_hit.is_(True)
        )
        cache_result = await self.db.execute(cache_stmt)
        cache_hits = cache_result.scalar() or 0
        cache_hit_rate = (cache_hits / total_requests * 100) if total_requests > 0 else 0.0

        strategy_stmt = (
            select(RequestLog.strategy, func.count(RequestLog.id))
            .where(RequestLog.created_at >= since)
            .group_by(RequestLog.strategy)
        )
        strategy_result = await self.db.execute(strategy_stmt)
        requests_by_strategy = {row[0]: row[1] for row in strategy_result.all()}

        model_stmt = (
            select(RequestLog.model_target, func.count(RequestLog.id))
            .where(RequestLog.created_at >= since, RequestLog.model_target.isnot(None))
            .group_by(RequestLog.model_target)
        )
        model_result = await self.db.execute(model_stmt)
        requests_by_model = {row[0]: row[1] for row in model_result.all()}

        recent_stmt = (
            select(RequestLog)
            .where(RequestLog.created_at >= since)
            .order_by(RequestLog.created_at.desc())
            .limit(20)
        )
        recent_result = await self.db.execute(recent_stmt)
        recent_logs = recent_result.scalars().all()

        recent_requests = [
            {
                "id": str(log.id),
                "endpoint": log.endpoint,
                "strategy": log.strategy,
                "tokens_before": log.tokens_before,
                "tokens_after": log.tokens_after,
                "tokens_saved": log.tokens_saved,
                "compression_ratio": log.compression_ratio,
                "latency_ms": log.latency_ms,
                "cache_hit": log.cache_hit,
                "created_at": log.created_at.isoformat(),
            }
            for log in recent_logs
        ]

        return {
            "total_requests": total_requests,
            "total_tokens_saved": int(total_tokens_saved),
            "total_cost_saved_usd": round(float(total_cost_saved), 4),
            "average_compression_ratio": round(float(avg_ratio), 4),
            "average_latency_ms": round(float(avg_latency), 2),
            "cache_hit_rate": round(cache_hit_rate, 2),
            "requests_by_strategy": requests_by_strategy,
            "requests_by_model": requests_by_model,
            "recent_requests": recent_requests,
        }

    async def analyze_content(self, messages: list[dict], target_model: str) -> dict[str, Any]:
        from app.schemas import CompressionStrategy
        from app.services.compression_service import CompressionService
        from app.services.router_service import RouterService

        token_svc = TokenService(target_model)
        tokens_before = token_svc.count_messages(messages)

        compression = CompressionService()
        router = RouterService()
        complexity = router.analyze_complexity(messages)
        task_type = router.detect_task_type(messages)

        estimated: dict[str, int] = {}
        savings: dict[str, float] = {}

        for strategy in CompressionStrategy:
            ratio_map = {
                "aggressive": 0.35, "balanced": 0.50, "ultra": 0.20,
                "semantic": 0.45, "code-focused": 0.60, "chat-focused": 0.48,
            }
            estimated_after = int(tokens_before * ratio_map.get(strategy.value, 0.5))
            estimated[strategy.value] = estimated_after
            saved = tokens_before - estimated_after
            savings[strategy.value] = round(saved / tokens_before * 100, 2) if tokens_before else 0

        recommended = CompressionStrategy.BALANCED
        if task_type == "coding":
            recommended = CompressionStrategy.CODE_FOCUSED
        elif task_type == "chat":
            recommended = CompressionStrategy.CHAT_FOCUSED
        elif complexity > 0.7:
            recommended = CompressionStrategy.SEMANTIC

        code_blocks = sum(
            1 for m in messages
            if isinstance(m.get("content"), str) and "```" in m["content"]
        )

        return {
            "tokens_before": tokens_before,
            "estimated_tokens_after": estimated,
            "estimated_savings": savings,
            "recommended_strategy": recommended,
            "complexity_score": complexity,
            "content_analysis": {
                "task_type": task_type,
                "message_count": len(messages),
                "code_blocks": code_blocks,
                "estimated_cost_usd": token_svc.estimate_cost(tokens_before, target_model),
            },
        }
