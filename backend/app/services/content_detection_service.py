"""Content type detection for specialized compression."""

import json
import re
from dataclasses import dataclass

from app.schemas import ContentType


@dataclass
class ContentAnalysis:
    content_type: ContentType
    confidence: float
    language: str | None = None
    subtypes: list[str] | None = None


class ContentDetectionService:
    CODE_FENCE = re.compile(r"```(\w*)\n")
    STACKTRACE = re.compile(
        r"(Traceback \(most recent call last\)|Exception in thread|at [\w.]+\([\w./]+:\d+\))",
        re.IGNORECASE,
    )
    LOG_LINE = re.compile(
        r"^\[?\d{4}[-/]\d{2}[-/]\d{2}|\d{2}:\d{2}:\d{2}|(?:INFO|DEBUG|WARN|ERROR|FATAL)\s",
        re.MULTILINE,
    )
    YAML_HEADER = re.compile(r"^[\w-]+:\s*[\w\"'.{[\]]", re.MULTILINE)
    XML_TAG = re.compile(r"<\?xml|<[\w:-]+[\s/>]")
    MD_HEADER = re.compile(r"^#{1,6}\s+\w", re.MULTILINE)
    MD_LIST = re.compile(r"^[\-*]\s+\w", re.MULTILINE)

    LANG_MAP = {
        "py": "python", "python": "python",
        "js": "javascript", "javascript": "javascript",
        "ts": "typescript", "typescript": "typescript",
        "tsx": "typescript", "jsx": "javascript",
        "java": "java", "go": "go", "rs": "rust",
        "rb": "ruby", "cpp": "cpp", "c": "c",
    }

    def detect(self, text: str) -> ContentAnalysis:
        if not text or not text.strip():
            return ContentAnalysis(ContentType.UNKNOWN, 0.0)

        scores: dict[ContentType, float] = {ct: 0.0 for ct in ContentType}

        if self.STACKTRACE.search(text):
            scores[ContentType.STACKTRACE] += 0.9
        if len(self.LOG_LINE.findall(text)) >= 3:
            scores[ContentType.LOGS] += 0.7

        code_blocks = self.CODE_FENCE.findall(text)
        if code_blocks or self._looks_like_code(text):
            scores[ContentType.CODE] += 0.8

        stripped = text.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                json.loads(stripped)
                scores[ContentType.JSON] += 0.95
            except json.JSONDecodeError:
                pass

        if self.XML_TAG.search(text):
            scores[ContentType.XML] += 0.8
        if self.YAML_HEADER.search(text) and ":" in text[:500]:
            scores[ContentType.YAML] += 0.6
        if self.MD_HEADER.search(text) or self.MD_LIST.search(text):
            scores[ContentType.MARKDOWN] += 0.7

        if scores[ContentType.CODE] > 0 and (
            scores[ContentType.MARKDOWN] > 0 or len(text) > 500
        ):
            scores[ContentType.MIXED] += 0.5

        doc_keywords = ["documentation", "readme", "guide", "tutorial", "overview"]
        if any(kw in text.lower()[:300] for kw in doc_keywords):
            scores[ContentType.DOCUMENTATION] += 0.5

        if max(scores.values()) < 0.4:
            scores[ContentType.CHAT] += 0.6

        best = max(scores, key=scores.get)  # type: ignore[arg-type]
        language = self._detect_language(text, code_blocks)

        return ContentAnalysis(
            content_type=best,
            confidence=min(scores[best], 1.0),
            language=language,
        )

    def detect_messages(self, messages: list[dict]) -> dict[int, ContentAnalysis]:
        return {
            i: self.detect(str(m.get("content", "")))
            for i, m in enumerate(messages)
        }

    def _detect_language(self, text: str, code_blocks: list[str]) -> str | None:
        for lang in code_blocks:
            if lang:
                return self.LANG_MAP.get(lang.lower(), lang.lower())
        for lang, name in self.LANG_MAP.items():
            if re.search(rf"\b(def |class |import |from |func |fn |const |let |var )\b", text):
                if lang in ("py", "python") and "def " in text or "import " in text:
                    return "python"
                if lang in ("js", "ts") and ("const " in text or "function " in text):
                    return "javascript"
        return None

    def _looks_like_code(self, text: str) -> bool:
        indicators = [
            r"^\s*(def|class|import|from|async def|function|const|let|var|public|private)\s",
            r"^\s*(if|for|while|return|try|except|catch)\s*[\(:]",
            r"[{};]\s*$",
        ]
        lines = text.splitlines()[:50]
        hits = sum(
            1 for line in lines
            if any(re.search(p, line) for p in indicators)
        )
        return hits >= 3
