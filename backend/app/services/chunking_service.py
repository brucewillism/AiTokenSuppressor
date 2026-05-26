"""Intelligent semantic and AST-based chunking."""

from dataclasses import dataclass

from app.core.config import get_settings
from app.schemas import ContentType
from app.services.ast_service import ASTService
from app.services.content_detection_service import ContentDetectionService

settings = get_settings()


@dataclass
class Chunk:
    content: str
    chunk_type: str
    index: int
    symbol_name: str | None = None
    source: str | None = None
    metadata: dict | None = None
    token_estimate: int = 0


class ChunkingService:
    def __init__(self) -> None:
        self.ast = ASTService()
        self.detector = ContentDetectionService()
        self.default_size = settings.rag_chunk_size
        self.overlap = settings.rag_chunk_overlap

    def chunk(
        self,
        content: str,
        source: str | None = None,
        language: str | None = None,
        use_ast: bool = True,
    ) -> list[Chunk]:
        analysis = self.detector.detect(content)
        lang = language or analysis.language or "text"

        if use_ast and analysis.content_type in (ContentType.CODE, ContentType.MIXED):
            return self._chunk_code(content, lang, source)
        if analysis.content_type == ContentType.MARKDOWN:
            return self._chunk_markdown(content, source)
        if analysis.content_type in (ContentType.JSON, ContentType.YAML, ContentType.XML):
            return self._chunk_structured(content, analysis.content_type.value, source)
        return self._chunk_semantic(content, source)

    def _chunk_code(self, content: str, language: str, source: str | None) -> list[Chunk]:
        ast_chunks = self.ast.chunk_by_ast(content, language)
        chunks: list[Chunk] = []
        for i, ac in enumerate(ast_chunks):
            chunk_content = ac["content"]
            if len(chunk_content) > self.default_size * 4:
                sub_chunks = self._split_with_overlap(chunk_content)
                for j, sub in enumerate(sub_chunks):
                    chunks.append(Chunk(
                        content=sub,
                        chunk_type=ac["chunk_type"],
                        index=len(chunks),
                        symbol_name=ac.get("symbol_name"),
                        source=source,
                        metadata={"sub_chunk": j, "dependencies": ac.get("dependencies", [])},
                        token_estimate=len(sub) // 4,
                    ))
            else:
                chunks.append(Chunk(
                    content=chunk_content,
                    chunk_type=ac["chunk_type"],
                    index=i,
                    symbol_name=ac.get("symbol_name"),
                    source=source,
                    metadata={"dependencies": ac.get("dependencies", [])},
                    token_estimate=len(chunk_content) // 4,
                ))
        return chunks

    def _chunk_markdown(self, content: str, source: str | None) -> list[Chunk]:
        import re
        sections = re.split(r"(?=^#{1,3}\s)", content, flags=re.MULTILINE)
        chunks: list[Chunk] = []
        current = ""
        for section in sections:
            if len(current) + len(section) <= self.default_size:
                current += section
            else:
                if current.strip():
                    chunks.append(Chunk(
                        content=current.strip(),
                        chunk_type="markdown_section",
                        index=len(chunks),
                        source=source,
                        token_estimate=len(current) // 4,
                    ))
                current = section
        if current.strip():
            chunks.append(Chunk(
                content=current.strip(),
                chunk_type="markdown_section",
                index=len(chunks),
                source=source,
                token_estimate=len(current) // 4,
            ))
        return chunks or self._chunk_semantic(content, source)

    def _chunk_structured(self, content: str, content_type: str, source: str | None) -> list[Chunk]:
        if len(content) <= self.default_size:
            return [Chunk(
                content=content, chunk_type=content_type, index=0,
                source=source, token_estimate=len(content) // 4,
            )]
        return [
            Chunk(content=c, chunk_type=content_type, index=i, source=source, token_estimate=len(c) // 4)
            for i, c in enumerate(self._split_with_overlap(content))
        ]

    def _chunk_semantic(self, content: str, source: str | None) -> list[Chunk]:
        paragraphs = content.split("\n\n")
        chunks: list[Chunk] = []
        current = ""
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if len(current) + len(para) + 2 <= self.default_size:
                current += ("\n\n" if current else "") + para
            else:
                if current:
                    chunks.append(Chunk(
                        content=current, chunk_type="paragraph", index=len(chunks),
                        source=source, token_estimate=len(current) // 4,
                    ))
                if len(para) > self.default_size:
                    for sub in self._split_with_overlap(para):
                        chunks.append(Chunk(
                            content=sub, chunk_type="paragraph", index=len(chunks),
                            source=source, token_estimate=len(sub) // 4,
                        ))
                    current = ""
                else:
                    current = para
        if current:
            chunks.append(Chunk(
                content=current, chunk_type="paragraph", index=len(chunks),
                source=source, token_estimate=len(current) // 4,
            ))
        return chunks

    def _split_with_overlap(self, text: str) -> list[str]:
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = start + self.default_size
            if end < len(text):
                break_point = text.rfind("\n", start, end)
                if break_point > start:
                    end = break_point
            chunks.append(text[start:end].strip())
            start = end - self.overlap if end < len(text) else end
        return [c for c in chunks if c]
