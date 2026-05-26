"""Streaming compression with incremental summarization."""

from collections.abc import AsyncGenerator
from dataclasses import dataclass

from app.schemas import CompressionStrategy
from app.services.compression_service import CompressionService
from app.services.hierarchical_summary_service import HierarchicalSummaryService
from app.services.token_service import TokenService


@dataclass
class StreamChunk:
    index: int
    messages: list[dict]
    tokens: int
    operation: str
    cumulative_savings: float


class StreamingService:
    def __init__(self) -> None:
        self.compression = CompressionService()
        self.summary = HierarchicalSummaryService()
        self.token_service = TokenService()

    async def compress_stream(
        self,
        messages: list[dict],
        strategy: CompressionStrategy = CompressionStrategy.BALANCED,
        chunk_size: int = 5,
    ) -> AsyncGenerator[StreamChunk, None]:
        tokens_before = self.token_service.count_messages(messages)
        accumulated: list[dict] = []
        processed = 0

        for i in range(0, len(messages), chunk_size):
            chunk = messages[i:i + chunk_size]
            accumulated.extend(chunk)

            if len(accumulated) > chunk_size * 2:
                older = accumulated[:-chunk_size]
                recent = accumulated[-chunk_size:]
                try:
                    summary_result = await self.summary.summarize_messages(older)
                    summary_msg = {
                        "role": "system",
                        "content": f"[Rolling summary]: {summary_result.final_summary}",
                    }
                    accumulated = [summary_msg] + recent
                    operation = "rolling_summary"
                except Exception:
                    compressed, _ = await self.compression.compress_prompt(
                        accumulated, strategy=strategy,
                    )
                    accumulated = compressed
                    operation = "chunk_compress"
            else:
                operation = "accumulate"

            current_tokens = self.token_service.count_messages(accumulated)
            savings = (1 - current_tokens / max(tokens_before, 1)) * 100

            yield StreamChunk(
                index=processed,
                messages=accumulated.copy(),
                tokens=current_tokens,
                operation=operation,
                cumulative_savings=round(savings, 2),
            )
            processed += 1

        final, _ = await self.compression.compress_prompt(accumulated, strategy=strategy)
        final_tokens = self.token_service.count_messages(final)
        yield StreamChunk(
            index=processed,
            messages=final,
            tokens=final_tokens,
            operation="final_compress",
            cumulative_savings=round((1 - final_tokens / max(tokens_before, 1)) * 100, 2),
        )

    async def compress_stream_collect(
        self,
        messages: list[dict],
        strategy: CompressionStrategy = CompressionStrategy.BALANCED,
        chunk_size: int = 5,
    ) -> tuple[list[dict], list[str]]:
        operations: list[str] = []
        result: list[dict] = messages
        async for chunk in self.compress_stream(messages, strategy, chunk_size):
            result = chunk.messages
            operations.append(chunk.operation)
        return result, operations
