"""Semantic loss detection after compression."""

from dataclasses import dataclass

from app.services.ollama_service import OllamaService
from app.services.quality_guard_service import QualityGuardService
from app.utils.helpers import cosine_similarity


@dataclass
class SemanticLossReport:
    loss_score: float  # 0 = no loss, 1 = total loss
    preservation_score: float
    embedding_similarity: float
    critical_preserved: bool
    quality_preserved: bool
    details: dict


class SemanticLossService:
    ACCEPTABLE_LOSS = 0.35

    def __init__(self) -> None:
        self.ollama = OllamaService()
        self.quality_guard = QualityGuardService()

    async def measure(
        self,
        original_messages: list[dict],
        compressed_messages: list[dict],
    ) -> SemanticLossReport:
        original_text = self._messages_to_text(original_messages)
        compressed_text = self._messages_to_text(compressed_messages)

        embedding_sim = await self._embedding_similarity(original_text, compressed_text)
        token_ratio = len(compressed_text) / max(len(original_text), 1)
        structural_sim = self._structural_similarity(original_messages, compressed_messages)

        quality_report = self.quality_guard.validate_compression(
            original_messages, compressed_messages
        )

        preservation = (
            embedding_sim * 0.45
            + structural_sim * 0.25
            + (1.0 if quality_report.quality_preserved else 0.3) * 0.30
        )
        loss_score = max(0.0, min(1.0, 1.0 - preservation))

        return SemanticLossReport(
            loss_score=round(loss_score, 4),
            preservation_score=round(preservation, 4),
            embedding_similarity=round(embedding_sim, 4),
            critical_preserved=quality_report.quality_preserved,
            quality_preserved=quality_report.quality_preserved,
            details={
                "token_ratio": round(token_ratio, 4),
                "structural_similarity": round(structural_sim, 4),
                "violations": quality_report.violations,
                "acceptable": loss_score <= self.ACCEPTABLE_LOSS,
            },
        )

    def is_acceptable(self, report: SemanticLossReport) -> bool:
        return report.loss_score <= self.ACCEPTABLE_LOSS and report.critical_preserved

    async def _embedding_similarity(self, text_a: str, text_b: str) -> float:
        try:
            emb_a = await self.ollama.create_embedding(text_a[:4000])
            emb_b = await self.ollama.create_embedding(text_b[:4000])
            return cosine_similarity(emb_a, emb_b)
        except Exception:
            words_a = set(text_a.lower().split())
            words_b = set(text_b.lower().split())
            if not words_a or not words_b:
                return 0.5
            return len(words_a & words_b) / len(words_a | words_b)

    def _structural_similarity(
        self, original: list[dict], compressed: list[dict],
    ) -> float:
        orig_roles = [m.get("role") for m in original]
        comp_roles = [m.get("role") for m in compressed]
        role_preservation = len(set(orig_roles) & set(comp_roles)) / max(len(set(orig_roles)), 1)
        count_ratio = len(compressed) / max(len(original), 1)
        count_sim = 1.0 - abs(1.0 - count_ratio) if count_ratio <= 1.0 else 0.5
        return (role_preservation + count_sim) / 2

    def _messages_to_text(self, messages: list[dict]) -> str:
        return "\n".join(
            f"[{m.get('role')}]: {m.get('content', '')}" for m in messages
        )
