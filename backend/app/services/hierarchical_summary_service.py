"""Hierarchical summarization: micro → macro summaries."""

from dataclasses import dataclass, field

from app.services.ollama_service import OllamaService


@dataclass
class SummaryLevel:
    level: str  # micro, meso, macro
    content: str
    source_count: int
    token_estimate: int


@dataclass
class HierarchicalSummary:
    levels: list[SummaryLevel] = field(default_factory=list)
    final_summary: str = ""


class HierarchicalSummaryService:
    MICRO_CHUNK = 3
    MESO_CHUNK = 5

    def __init__(self) -> None:
        self.ollama = OllamaService()

    async def summarize_messages(self, messages: list[dict]) -> HierarchicalSummary:
        texts = [
            f"[{m.get('role')}]: {str(m.get('content', ''))[:800]}"
            for m in messages if m.get("content")
        ]
        if not texts:
            return HierarchicalSummary(final_summary="")

        if len(texts) <= self.MICRO_CHUNK:
            combined = "\n".join(texts)
            try:
                summary = await self.ollama.summarize(combined, max_words=150)
            except Exception:
                summary = combined[:500]
            return HierarchicalSummary(
                levels=[SummaryLevel("macro", summary, len(texts), len(summary) // 4)],
                final_summary=summary,
            )

        micro_summaries: list[SummaryLevel] = []
        for i in range(0, len(texts), self.MICRO_CHUNK):
            chunk = texts[i:i + self.MICRO_CHUNK]
            combined = "\n".join(chunk)
            try:
                micro = await self.ollama.summarize(combined, max_words=60)
            except Exception:
                micro = combined[:200]
            micro_summaries.append(SummaryLevel("micro", micro, len(chunk), len(micro) // 4))

        meso_summaries: list[SummaryLevel] = []
        micro_texts = [m.content for m in micro_summaries]
        for i in range(0, len(micro_texts), self.MESO_CHUNK):
            chunk = micro_texts[i:i + self.MESO_CHUNK]
            combined = "\n".join(chunk)
            try:
                meso = await self.ollama.summarize(combined, max_words=100)
            except Exception:
                meso = combined[:300]
            meso_summaries.append(SummaryLevel("meso", meso, len(chunk), len(meso) // 4))

        macro_input = "\n".join(m.content for m in meso_summaries)
        try:
            macro = await self.ollama.summarize(macro_input, max_words=200)
        except Exception:
            macro = macro_input[:500]

        macro_level = SummaryLevel("macro", macro, len(meso_summaries), len(macro) // 4)

        return HierarchicalSummary(
            levels=micro_summaries + meso_summaries + [macro_level],
            final_summary=macro,
        )

    async def summarize_text(self, text: str, max_levels: int = 3) -> str:
        if len(text) < 500:
            return text
        result = await self.summarize_messages([{"role": "user", "content": text}])
        return result.final_summary
