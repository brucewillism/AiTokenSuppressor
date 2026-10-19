"""Quality preservation - never lose critical instructions."""

import re
from dataclasses import dataclass, field

from ats_core.relevance import RelevanceService


@dataclass
class PreservedBlock:
    content: str
    reason: str
    priority: int
    original_index: int


@dataclass
class QualityReport:
    preserved: list[PreservedBlock] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    quality_preserved: bool = True


OUTPUT_CONTRACT_PATTERNS = [
    r"return (?:only|just)\s+(?:json|xml|yaml|markdown)",
    r"output (?:format|must be|should be)",
    r"respond (?:with|in)\s+(?:json|xml|markdown)",
    r"```json\s*\{",
    r"\"(?:type|format|schema|properties)\"\s*:",
    r"<\/?(?:response|output|format)",
]

SYSTEM_PROMPT_MIN_LENGTH = 20


def _last_user_index(messages: list[dict]) -> int | None:
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if isinstance(message, dict) and message.get("role") == "user":
            return index
    return None


class QualityGuardService:
    def __init__(self) -> None:
        self.relevance = RelevanceService()

    def extract_critical_blocks(self, messages: list[dict]) -> list[PreservedBlock]:
        preserved: list[PreservedBlock] = []
        for i, msg in enumerate(messages):
            content = str(msg.get("content", ""))
            role = msg.get("role", "")

            if role == "system":
                score = self.relevance.score_message(msg)
                if score.is_critical or len(content) >= SYSTEM_PROMPT_MIN_LENGTH:
                    preserved.append(PreservedBlock(
                        content=content,
                        reason="system_prompt",
                        priority=100,
                        original_index=i,
                    ))
                    continue

            for pattern in OUTPUT_CONTRACT_PATTERNS:
                if re.search(pattern, content, re.IGNORECASE):
                    preserved.append(PreservedBlock(
                        content=content,
                        reason="output_contract",
                        priority=90,
                        original_index=i,
                    ))
                    break

            score = self.relevance.score_message(msg)
            if score.is_critical:
                preserved.append(PreservedBlock(
                    content=content,
                    reason="critical_instruction",
                    priority=95,
                    original_index=i,
                ))

        return preserved

    def merge_with_compressed(
        self,
        original: list[dict],
        compressed: list[dict],
    ) -> tuple[list[dict], QualityReport]:
        report = QualityReport()
        critical = self.extract_critical_blocks(original)
        report.preserved = critical

        if not critical:
            return compressed, report

        compressed_contents = {
            str(m.get("content", "")).strip()
            for m in compressed
        }

        result = list(compressed)
        system_msgs = [m for m in result if m.get("role") == "system"]
        other_msgs = [m for m in result if m.get("role") != "system"]

        for block in sorted(critical, key=lambda b: b.priority, reverse=True):
            if block.content.strip() not in compressed_contents:
                if block.reason == "system_prompt":
                    if not any(
                        block.content[:100] in str(m.get("content", ""))
                        for m in system_msgs
                    ):
                        system_msgs.insert(0, {"role": "system", "content": block.content})
                        report.violations.append(
                            f"restored_system_prompt:index_{block.original_index}"
                        )
                else:
                    system_msgs.append({
                        "role": "system",
                        "content": f"[Preserved {block.reason}]: {block.content}",
                    })
                    report.violations.append(
                        f"restored_{block.reason}:index_{block.original_index}"
                    )

        report.quality_preserved = len(report.violations) == 0 or all(
            "restored" in v for v in report.violations
        )
        return self.anchor_final_user_turn(original, system_msgs + other_msgs), report

    def anchor_final_user_turn(self, original: list[dict], compressed: list[dict]) -> list[dict]:
        """Keep the final user turn verbatim and last when it closed the prompt.

        Identity is the same dict that entered compression. A rewritten copy is not
        invented here; the compressor restores bytes on that object before merging.
        """
        index = _last_user_index(original)
        if index is None:
            return compressed
        source = original[index]
        was_last = index == len(original) - 1
        present = any(message is source for message in compressed)
        if was_last:
            if present:
                return [message for message in compressed if message is not source] + [source]
            return [*compressed, source]
        if present:
            return compressed
        spot = min(index, len(compressed))
        return [*compressed[:spot], source, *compressed[spot:]]

    def validate_compression(
        self,
        original: list[dict],
        compressed: list[dict],
    ) -> QualityReport:
        report = QualityReport()
        critical = self.extract_critical_blocks(original)
        report.preserved = critical

        compressed_text = " ".join(str(m.get("content", "")) for m in compressed)

        for block in critical:
            key_fragment = block.content[:80].strip()
            if key_fragment and key_fragment not in compressed_text:
                report.violations.append(
                    f"missing_critical:{block.reason}:index_{block.original_index}"
                )

        report.quality_preserved = len(report.violations) == 0
        return report

    def protect_during_compression(self, messages: list[dict]) -> tuple[list[dict], list[dict]]:
        """Split messages into protected (do not compress) and compressible."""
        protected: list[dict] = []
        compressible: list[dict] = []
        critical_indices = {b.original_index for b in self.extract_critical_blocks(messages)}

        for i, msg in enumerate(messages):
            if i in critical_indices or msg.get("role") == "system":
                score = self.relevance.score_message(msg)
                if score.is_critical or msg.get("role") == "system":
                    protected.append(msg)
                    continue
            compressible.append(msg)

        return protected, compressible
