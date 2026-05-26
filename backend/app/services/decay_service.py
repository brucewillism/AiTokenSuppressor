"""Relevance decay over time."""

import math
from datetime import UTC, datetime

from app.core.config import get_settings

settings = get_settings()


class DecayService:
    HALF_LIFE_HOURS = 168  # 7 days default

    def __init__(self, half_life_hours: float | None = None) -> None:
        self.half_life = half_life_hours or self.HALF_LIFE_HOURS

    def decay_score(
        self,
        created_at: datetime,
        base_score: float = 1.0,
        access_count: int = 0,
        memory_type: str = "context",
    ) -> float:
        age_hours = max(0, (datetime.now(UTC) - created_at).total_seconds() / 3600)
        time_decay = math.exp(-0.693 * age_hours / self.half_life)

        access_boost = min(1.0 + access_count * 0.05, 1.5)

        type_weights = {
            "preference": 1.3,
            "decision": 1.2,
            "context": 1.0,
            "prompt": 0.8,
            "response": 0.7,
        }
        type_weight = type_weights.get(memory_type, 1.0)

        return min(base_score * time_decay * access_boost * type_weight, 1.0)

    def apply_decay_to_scores(
        self,
        items: list[tuple[any, float, datetime | None, int, str]],
    ) -> list[tuple[any, float]]:
        result: list[tuple[any, float]] = []
        for item, score, created_at, access_count, memory_type in items:
            if created_at:
                decayed = score * self.decay_score(created_at, 1.0, access_count, memory_type)
            else:
                decayed = score * 0.8
            result.append((item, decayed))
        result.sort(key=lambda x: x[1], reverse=True)
        return result

    def freshness_score(self, created_at: datetime | None) -> float:
        if not created_at:
            return 0.7
        return self.decay_score(created_at, 1.0)

    def should_consolidate(self, created_at: datetime, access_count: int) -> bool:
        age_days = (datetime.now(UTC) - created_at).days
        return age_days > 30 and access_count < 3

    def adaptive_importance(
        self,
        base_score: float,
        created_at: datetime,
        last_accessed: datetime | None,
        access_count: int,
    ) -> float:
        decay = self.decay_score(created_at, base_score, access_count)
        if last_accessed:
            recency_hours = (datetime.now(UTC) - last_accessed).total_seconds() / 3600
            if recency_hours < 24:
                decay = min(decay * 1.3, 1.0)
        return decay
