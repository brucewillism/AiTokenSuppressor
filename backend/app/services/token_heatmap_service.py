"""Token heatmap generation."""

from app.services.content_detection_service import ContentDetectionService
from app.services.relevance_service import RelevanceService
from app.services.token_service import TokenService


class TokenHeatmapService:
    COMPRESSIBLE_TYPES = {"logs", "chat", "documentation", "stacktrace"}

    def __init__(self) -> None:
        self.token_service = TokenService()
        self.detector = ContentDetectionService()
        self.relevance = RelevanceService()

    def generate(self, messages: list[dict], model: str = "default") -> dict:
        token_svc = TokenService(model)
        total = token_svc.count_messages(messages)
        segments: list[dict] = []
        hotspots: list[str] = []

        for i, msg in enumerate(messages):
            content = str(msg.get("content", ""))
            tokens = token_svc.count_tokens(content) + 4
            percent = (tokens / total * 100) if total > 0 else 0
            analysis = self.detector.detect(content)
            score = self.relevance.score_message(msg)

            label = f"{msg.get('role', '?')}:{analysis.content_type.value}"
            compressible = (
                analysis.content_type.value in self.COMPRESSIBLE_TYPES
                and not score.is_critical
            )

            if percent > 15:
                hotspots.append(f"{label} ({tokens} tokens, {percent:.1f}%)")

            segments.append({
                "index": i,
                "role": msg.get("role", "unknown"),
                "content_type": analysis.content_type.value,
                "tokens": tokens,
                "percent": round(percent, 2),
                "label": label,
                "compressible": compressible,
                "is_critical": score.is_critical,
                "relevance_score": round(score.total, 3),
            })

        segments.sort(key=lambda s: s["tokens"], reverse=True)
        return {
            "total_tokens": total,
            "segments": segments,
            "hotspots": hotspots[:10],
        }
