"""Memory consolidation - merge similar memories."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.fingerprint_service import FingerprintService
from app.services.ollama_service import OllamaService


@dataclass
class ConsolidationResult:
    merged_count: int
    removed_ids: list[str]
    consolidated_content: str


class ConsolidationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.fingerprint = FingerprintService(threshold=0.80)
        self.ollama = OllamaService()

    async def find_similar_groups(
        self, memories: list[dict],
    ) -> list[list[dict]]:
        groups: list[list[dict]] = []
        assigned: set[int] = set()

        for i, mem_a in enumerate(memories):
            if i in assigned:
                continue
            group = [mem_a]
            assigned.add(i)
            content_a = mem_a.get("content", "")

            for j, mem_b in enumerate(memories):
                if j in assigned:
                    continue
                content_b = mem_b.get("content", "")
                if self.fingerprint.is_near_duplicate(content_a, content_b):
                    group.append(mem_b)
                    assigned.add(j)

            if len(group) > 1:
                groups.append(group)

        return groups

    async def consolidate_group(self, group: list[dict]) -> ConsolidationResult:
        contents = [m.get("content", "") for m in group]
        combined = "\n---\n".join(contents)

        try:
            consolidated = await self.ollama.summarize(combined, max_words=120)
        except Exception:
            consolidated = contents[0]

        removed = [str(m.get("id", "")) for m in group[1:]]

        return ConsolidationResult(
            merged_count=len(group),
            removed_ids=removed,
            consolidated_content=consolidated,
        )

    async def consolidate_memories(
        self, memories: list[dict],
    ) -> list[ConsolidationResult]:
        groups = await self.find_similar_groups(memories)
        results: list[ConsolidationResult] = []
        for group in groups:
            result = await self.consolidate_group(group)
            results.append(result)
        return results
