"""Deduplication engine using hashing and similarity."""

import re
from typing import Any

from app.core.logging import get_logger
from app.services.ollama_service import OllamaService
from app.services.token_service import TokenService
from app.utils.helpers import content_hash, extract_code_blocks, fingerprint

logger = get_logger(__name__)


class DeduplicationService:
    def __init__(self) -> None:
        self.ollama = OllamaService()
        self.token_service = TokenService()
        self._content_hashes: dict[str, str] = {}
        self._code_hashes: dict[str, int] = {}

    def hash_content(self, content: str) -> str:
        return content_hash(content)

    def fingerprint_content(self, content: str) -> str:
        return fingerprint(content)

    def deduplicate_messages(self, messages: list[dict[str, Any]]) -> tuple[list[dict], list[str]]:
        seen_hashes: set[str] = set()
        seen_fingerprints: set[str] = set()
        deduplicated: list[dict] = []
        operations: list[str] = []

        for msg in messages:
            content = msg.get("content", "")
            if not isinstance(content, str):
                deduplicated.append(msg)
                continue

            h = self.hash_content(content)
            fp = self.fingerprint_content(content)

            if h in seen_hashes or fp in seen_fingerprints:
                operations.append(f"removed_duplicate_message:{msg.get('role', 'unknown')}")
                continue

            seen_hashes.add(h)
            seen_fingerprints.add(fp)
            deduplicated.append(msg)

        return deduplicated, operations

    def deduplicate_code_blocks(self, text: str) -> tuple[str, list[str]]:
        blocks = extract_code_blocks(text)
        if not blocks:
            return text, []

        seen: set[str] = set()
        operations: list[str] = []
        result = text

        for lang, code in blocks:
            code_hash = content_hash(code.strip())
            if code_hash in seen:
                block_pattern = f"```{lang}\n{re.escape(code)}```"
                replacement = f"```{lang}\n# [duplicate code block removed - hash:{code_hash[:8]}]\n```"
                result = re.sub(block_pattern, replacement, result, count=1)
                operations.append(f"deduplicated_code_block:{lang or 'plain'}")
            else:
                seen.add(code_hash)

        return result, operations

    def deduplicate_files_in_context(self, text: str) -> tuple[str, list[str]]:
        file_pattern = r"(?:File:|Path:|---\s)([\w./\\-]+\.\w+)\s*\n(.*?)(?=(?:File:|Path:|---\s|$))"
        matches = re.findall(file_pattern, text, re.DOTALL)
        if not matches:
            return text, []

        seen_files: dict[str, str] = {}
        operations: list[str] = []
        result = text

        for filepath, content in matches:
            h = content_hash(content.strip())
            if filepath in seen_files:
                if seen_files[filepath] == h:
                    pattern = rf"(?:File:|Path:|---\s){re.escape(filepath)}\s*\n{re.escape(content.strip()[:100])}"
                    result = re.sub(
                        pattern,
                        f"[File: {filepath} - duplicate removed]",
                        result,
                        count=1,
                    )
                    operations.append(f"deduplicated_file:{filepath}")
            else:
                seen_files[filepath] = h

        return result, operations

    async def find_near_duplicates(
        self, messages: list[dict[str, Any]], threshold: float = 0.85
    ) -> tuple[list[dict], list[str]]:
        if len(messages) < 2:
            return messages, []

        contents = [
            m.get("content", "") for m in messages if isinstance(m.get("content"), str)
        ]
        if not contents:
            return messages, []

        try:
            redundant_indices = await self.ollama.detect_redundancy(contents)
        except Exception:
            redundant_indices = []

        if not redundant_indices:
            return messages, []

        operations: list[str] = []
        keep_indices = set(range(len(messages)))
        content_idx = 0
        for i, msg in enumerate(messages):
            if isinstance(msg.get("content"), str):
                if content_idx in redundant_indices:
                    keep_indices.discard(i)
                    operations.append(f"semantic_dedup_index:{i}")
                content_idx += 1

        return [messages[i] for i in sorted(keep_indices)], operations

    def deduplicate_content(self, text: str) -> tuple[str, list[str]]:
        all_ops: list[str] = []
        result = text

        result, code_ops = self.deduplicate_code_blocks(result)
        all_ops.extend(code_ops)

        result, file_ops = self.deduplicate_files_in_context(result)
        all_ops.extend(file_ops)

        lines = result.splitlines()
        seen_lines: set[str] = set()
        unique_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped and len(stripped) > 20:
                h = content_hash(stripped)
                if h in seen_lines:
                    all_ops.append("deduplicated_line")
                    continue
                seen_lines.add(h)
            unique_lines.append(line)

        return "\n".join(unique_lines), all_ops
