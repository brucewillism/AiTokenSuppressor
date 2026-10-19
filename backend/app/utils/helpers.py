"""Funções puras de texto. A implementação vive em ats_core."""

from ats_core.textutil import (
    compact_json,
    content_hash,
    cosine_similarity,
    extract_code_blocks,
    fingerprint,
    messages_to_text,
    minify_whitespace,
    parse_json_safe,
    remove_duplicate_lines,
    remove_stack_trace_duplicates,
    truncate_smart,
)

__all__ = [
    "compact_json",
    "content_hash",
    "cosine_similarity",
    "extract_code_blocks",
    "fingerprint",
    "messages_to_text",
    "minify_whitespace",
    "parse_json_safe",
    "remove_duplicate_lines",
    "remove_stack_trace_duplicates",
    "truncate_smart",
]
