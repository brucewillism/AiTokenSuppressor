"""Compression benchmark system."""

import time
from dataclasses import dataclass

from app.schemas import CompressionStrategy
from app.services.compression_service import CompressionService
from app.services.semantic_loss_service import SemanticLossService
from app.services.token_service import TokenService


@dataclass
class BenchmarkEntry:
    strategy: str
    tokens_before: int
    tokens_after: int
    compression_ratio: float
    savings_percent: float
    semantic_loss_score: float
    latency_ms: float
    quality_preserved: bool
    balance_score: float


class BenchmarkService:
    def __init__(self) -> None:
        self.compression = CompressionService()
        self.semantic_loss = SemanticLossService()
        self.token_service = TokenService()

    async def run(
        self,
        messages: list[dict],
        strategies: list[CompressionStrategy] | None = None,
        target_model: str = "claude-3-5-sonnet",
    ) -> tuple[list[BenchmarkEntry], str, float]:
        strategies = strategies or list(CompressionStrategy)
        tokens_before = self.token_service.count_messages(messages)
        entries: list[BenchmarkEntry] = []

        for strategy in strategies:
            start = time.perf_counter()
            compressed, _ops = await self.compression.compress_prompt(
                messages, strategy=strategy,
            )
            latency = (time.perf_counter() - start) * 1000
            tokens_after = self.token_service.count_messages(compressed)
            savings = self.token_service.estimate_savings(tokens_before, tokens_after)

            loss_report = await self.semantic_loss.measure(messages, compressed)

            balance = (
                savings["savings_percent"] / 100 * 0.5
                + loss_report.preservation_score * 0.5
            )

            entries.append(BenchmarkEntry(
                strategy=strategy.value,
                tokens_before=tokens_before,
                tokens_after=tokens_after,
                compression_ratio=savings["compression_ratio"],
                savings_percent=savings["savings_percent"],
                semantic_loss_score=loss_report.loss_score,
                latency_ms=round(latency, 2),
                quality_preserved=loss_report.quality_preserved,
                balance_score=round(balance, 4),
            ))

        entries.sort(key=lambda e: e.balance_score, reverse=True)
        best = entries[0] if entries else None
        return entries, best.strategy if best else "balanced", best.balance_score if best else 0.0
