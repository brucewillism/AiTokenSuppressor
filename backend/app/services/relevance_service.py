"""Semantic importance and relevance scoring."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from app.schemas import ContentType
from app.services.content_detection_service import ContentDetectionService


@dataclass
class RelevanceScore:
    total: float
    relevance: float
    freshness: float
    instruction_priority: float
    persistence: float
    contextual_weight: float
    is_critical: bool


CRITICAL_PATTERNS = [
    r"\b(MUST|NEVER|ALWAYS|REQUIRED|CRITICAL|MANDATORY)\b",
    r"\b(do not|must not|should not|never)\b",
    r"\b(output format|response format|json schema|return only)\b",
    r"\b(system prompt|you are|your role|instructions:)\b",
    r"\b(constraint|rule|policy|guideline)\b",
    r"```json\s*\{[^}]*\"(?:type|format|schema)\"",
]

DISCARDABLE_PATTERNS = [
    r"^(ok|thanks|thank you|got it|sure|yes|no|hello|hi)\.?$",
    r"^(please note that|it is important to remember)",
    r"^\s*---+\s*$",
]


class RelevanceService:
    def __init__(self) -> None:
        self.content_detector = ContentDetectionService()

    def score_message(
        self,
        message: dict,
        recent_context: str = "",
        created_at: datetime | None = None,
    ) -> RelevanceScore:
        content = str(message.get("content", ""))
        role = message.get("role", "user")

        relevance = self._relevance_score(content, recent_context, role)
        freshness = self._freshness_score(created_at)
        instruction = self._instruction_priority(content, role)
        persistence = self._persistence_score(content, role)
        contextual = self._contextual_weight(content, recent_context)
        is_critical = instruction > 0.8 or self._is_critical_instruction(content)

        total = (
            relevance * 0.30
            + freshness * 0.15
            + instruction * 0.25
            + persistence * 0.15
            + contextual * 0.15
        )
        if is_critical:
            total = max(total, 0.95)

        return RelevanceScore(
            total=min(total, 1.0),
            relevance=relevance,
            freshness=freshness,
            instruction_priority=instruction,
            persistence=persistence,
            contextual_weight=contextual,
            is_critical=is_critical,
        )

    def rank_messages(
        self,
        messages: list[dict],
        recent_context: str = "",
    ) -> list[tuple[int, RelevanceScore]]:
        scored = [
            (i, self.score_message(m, recent_context))
            for i, m in enumerate(messages)
        ]
        scored.sort(key=lambda x: x[1].total, reverse=True)
        return scored

    def filter_discardable(self, messages: list[dict]) -> tuple[list[dict], list[int]]:
        kept: list[dict] = []
        removed: list[int] = []
        for i, msg in enumerate(messages):
            content = str(msg.get("content", "")).strip()
            score = self.score_message(msg)
            if score.is_critical:
                kept.append(msg)
                continue
            if any(re.match(p, content, re.IGNORECASE) for p in DISCARDABLE_PATTERNS):
                removed.append(i)
                continue
            if score.total < 0.2 and msg.get("role") != "system":
                removed.append(i)
                continue
            kept.append(msg)
        return kept, removed

    def _relevance_score(self, content: str, context: str, role: str) -> float:
        score = 0.5
        if role == "system":
            score += 0.25
        if not context:
            return min(score, 1.0)
        words = set(context.lower().split())
        content_words = set(content.lower().split())
        overlap = len(words & content_words) / max(len(words), 1)
        score += min(overlap * 0.5, 0.4)
        if "?" in content:
            score += 0.1
        analysis = self.content_detector.detect(content)
        if analysis.content_type == ContentType.CODE:
            score += 0.15
        return min(score, 1.0)

    def _freshness_score(self, created_at: datetime | None) -> float:
        if not created_at:
            return 0.7
        age_hours = (datetime.now(UTC) - created_at).total_seconds() / 3600
        if age_hours < 1:
            return 1.0
        if age_hours < 24:
            return 0.85
        if age_hours < 168:
            return 0.6
        return max(0.2, 1.0 - age_hours / 720)

    def _instruction_priority(self, content: str, role: str) -> float:
        score = 0.3 if role == "system" else 0.1
        for pattern in CRITICAL_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                score += 0.2
        if role == "system" and len(content) > 50:
            score += 0.3
        return min(score, 1.0)

    def _persistence_score(self, content: str, role: str) -> float:
        persistent_keywords = [
            "preference", "always use", "never use", "default", "remember",
            "decision", "architecture", "pattern", "convention", "standard",
        ]
        score = 0.4 if role == "system" else 0.2
        content_lower = content.lower()
        hits = sum(1 for kw in persistent_keywords if kw in content_lower)
        score += min(hits * 0.15, 0.5)
        return min(score, 1.0)

    def _contextual_weight(self, content: str, context: str) -> float:
        if not context:
            return 0.5
        important_terms = re.findall(r"\b[A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)*\b", context)
        if not important_terms:
            return 0.5
        hits = sum(1 for term in important_terms[:20] if term.lower() in content.lower())
        return min(0.3 + hits * 0.1, 1.0)

    def _is_critical_instruction(self, content: str) -> bool:
        return any(re.search(p, content, re.IGNORECASE) for p in CRITICAL_PATTERNS)
