"""Utility functions."""

import hashlib
import json
import re
from typing import Any

import orjson


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def fingerprint(content: str) -> str:
    normalized = re.sub(r"\s+", " ", content.strip().lower())
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


def compact_json(data: Any, max_length: int = 2000) -> str:
    try:
        text = orjson.dumps(data).decode("utf-8")
    except (TypeError, ValueError):
        text = str(data)
    if len(text) > max_length:
        return text[:max_length] + "...[truncated]"
    return text


def remove_duplicate_lines(text: str) -> str:
    seen: set[str] = set()
    result: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and stripped not in seen:
            seen.add(stripped)
            result.append(line)
        elif not stripped:
            result.append(line)
    return "\n".join(result)


def remove_stack_trace_duplicates(text: str) -> str:
    pattern = r"(Traceback \(most recent call last\):.*?)(?=\nTraceback|\Z)"
    traces = re.findall(pattern, text, re.DOTALL)
    if len(traces) <= 1:
        return text
    unique: list[str] = []
    seen_hashes: set[str] = set()
    for trace in traces:
        h = content_hash(trace)
        if h not in seen_hashes:
            seen_hashes.add(h)
            unique.append(trace)
    return text.split("Traceback")[0] + "\n".join(
        f"Traceback{t}" if not t.startswith("(") else t for t in unique
    )


def minify_whitespace(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    result: list[str] = []
    blank_count = 0
    for line in lines:
        if not line.strip():
            blank_count += 1
            if blank_count <= 1:
                result.append("")
        else:
            blank_count = 0
            result.append(line)
    return "\n".join(result).strip()


def truncate_smart(text: str, max_chars: int, preserve_end: bool = False) -> str:
    if len(text) <= max_chars:
        return text
    if preserve_end:
        return "..." + text[-(max_chars - 3):]
    half = (max_chars - 3) // 2
    return text[:half] + "..." + text[-half:]


def extract_code_blocks(text: str) -> list[tuple[str, str]]:
    pattern = r"```(\w*)\n(.*?)```"
    return re.findall(pattern, text, re.DOTALL)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def messages_to_text(messages: list[dict[str, Any]]) -> str:
    parts = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        parts.append(f"[{role}]: {content}")
    return "\n\n".join(parts)


def parse_json_safe(text: str) -> Any:
    try:
        return orjson.loads(text)
    except (orjson.JSONDecodeError, ValueError):
        return None
