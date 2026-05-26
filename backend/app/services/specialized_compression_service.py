"""Content-type specialized compression."""

import json
import re

from app.schemas import ContentType
from app.services.ast_service import ASTService
from app.services.content_detection_service import ContentDetectionService
from app.utils.helpers import (
    compact_json,
    minify_whitespace,
    remove_duplicate_lines,
    remove_stack_trace_duplicates,
)


class SpecializedCompressionService:
    def __init__(self) -> None:
        self.detector = ContentDetectionService()
        self.ast = ASTService()

    def compress(self, text: str, content_type: ContentType | None = None) -> tuple[str, list[str]]:
        analysis = self.detector.detect(text) if content_type is None else None
        ct = content_type or (analysis.content_type if analysis else ContentType.UNKNOWN)

        compressors = {
            ContentType.CODE: self._compress_code,
            ContentType.LOGS: self._compress_logs,
            ContentType.STACKTRACE: self._compress_stacktrace,
            ContentType.JSON: self._compress_json,
            ContentType.YAML: self._compress_yaml,
            ContentType.XML: self._compress_xml,
            ContentType.MARKDOWN: self._compress_markdown,
            ContentType.CHAT: self._compress_chat,
            ContentType.DOCUMENTATION: self._compress_documentation,
            ContentType.MIXED: self._compress_mixed,
        }

        compressor = compressors.get(ct, self._compress_generic)
        return compressor(text)

    def compress_message(self, content: str) -> tuple[str, list[str], ContentType]:
        analysis = self.detector.detect(content)
        compressed, ops = self.compress(content, analysis.content_type)
        return compressed, ops, analysis.content_type

    def _compress_code(self, text: str) -> tuple[str, list[str]]:
        ops = ["specialized:code"]
        lang = self.detector.detect(text).language or "python"
        if "```" in text:
            def replace_block(match: re.Match[str]) -> str:
                lang_tag = match.group(1) or lang
                code = match.group(2)
                compressed = self.ast.compress_code(code, lang_tag)
                return f"```{lang_tag}\n{compressed}\n```"
            result = re.sub(r"```(\w*)\n(.*?)```", replace_block, text, flags=re.DOTALL)
            ops.append("ast_code_blocks")
            return result, ops
        return self.ast.compress_code(text, lang), ops

    def _compress_logs(self, text: str) -> tuple[str, list[str]]:
        lines = text.splitlines()
        seen: set[str] = set()
        result: list[str] = []
        for line in lines:
            normalized = re.sub(r"\d{4}-\d{2}-\d{2}|\d{2}:\d{2}:\d{2}", "<TS>", line)
            if normalized not in seen:
                seen.add(normalized)
                result.append(line)
        if len(result) > 50:
            result = result[:10] + ["... [truncated log lines] ..."] + result[-10:]
        return "\n".join(result), ["specialized:logs", "dedup_timestamps"]

    def _compress_stacktrace(self, text: str) -> tuple[str, list[str]]:
        compressed = remove_stack_trace_duplicates(text)
        lines = compressed.splitlines()
        if len(lines) > 30:
            compressed = "\n".join(lines[:5] + ["... [stack frames omitted] ..."] + lines[-5:])
        return compressed, ["specialized:stacktrace"]

    def _compress_json(self, text: str) -> tuple[str, list[str]]:
        try:
            data = json.loads(text.strip())
            return compact_json(data, max_length=2000), ["specialized:json"]
        except json.JSONDecodeError:
            return compact_json(text, max_length=2000), ["specialized:json_fallback"]

    def _compress_yaml(self, text: str) -> tuple[str, list[str]]:
        lines = [l for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
        if len(lines) > 40:
            lines = lines[:20] + ["# ... truncated ..."] + lines[-10:]
        return "\n".join(lines), ["specialized:yaml"]

    def _compress_xml(self, text: str) -> tuple[str, list[str]]:
        compressed = re.sub(r">\s+<", "><", text)
        compressed = re.sub(r"\s{2,}", " ", compressed)
        if len(compressed) > 3000:
            compressed = compressed[:3000] + "...[truncated]"
        return compressed, ["specialized:xml"]

    def _compress_markdown(self, text: str) -> tuple[str, list[str]]:
        result = minify_whitespace(text)
        result = re.sub(r"\n{3,}", "\n\n", result)
        return result, ["specialized:markdown"]

    def _compress_chat(self, text: str) -> tuple[str, list[str]]:
        result, _ = self._compress_generic(text)
        verbose = [
            (r"please note that\s+", ""),
            (r"it is important to (?:note|remember) that\s+", ""),
            (r"as mentioned (?:above|earlier),?\s*", ""),
        ]
        for pattern, repl in verbose:
            result = re.sub(pattern, repl, result, flags=re.IGNORECASE)
        return result, ["specialized:chat"]

    def _compress_documentation(self, text: str) -> tuple[str, list[str]]:
        lines = text.splitlines()
        headers = [l for l in lines if l.startswith("#")]
        body = [l for l in lines if not l.startswith("#") and l.strip()]
        summary = "\n".join(headers + body[:30])
        if len(body) > 30:
            summary += "\n... [documentation truncated] ..."
        return summary, ["specialized:documentation"]

    def _compress_mixed(self, text: str) -> tuple[str, list[str]]:
        parts = re.split(r"(```[\s\S]*?```)", text)
        result_parts: list[str] = []
        all_ops: list[str] = ["specialized:mixed"]
        for part in parts:
            if part.startswith("```"):
                compressed, ops = self._compress_code(part)
                result_parts.append(compressed)
                all_ops.extend(ops)
            else:
                compressed, ops = self._compress_chat(part)
                result_parts.append(compressed)
                all_ops.extend(ops)
        return "".join(result_parts), all_ops

    def _compress_generic(self, text: str) -> tuple[str, list[str]]:
        result = minify_whitespace(text)
        result = remove_duplicate_lines(result)
        return result, ["specialized:generic"]
