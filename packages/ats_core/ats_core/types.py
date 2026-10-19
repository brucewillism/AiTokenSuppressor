"""Enums do núcleo. Os valores coincidem com os do serviço HTTP."""

from enum import Enum


class CompressionStrategy(str, Enum):
    FAST = "fast"
    AGGRESSIVE = "aggressive"
    BALANCED = "balanced"
    ULTRA = "ultra"
    SEMANTIC = "semantic"
    CODE_FOCUSED = "code-focused"
    CHAT_FOCUSED = "chat-focused"


class ContentType(str, Enum):
    CODE = "code"
    LOGS = "logs"
    MARKDOWN = "markdown"
    JSON = "json"
    XML = "xml"
    YAML = "yaml"
    STACKTRACE = "stacktrace"
    CHAT = "chat"
    DOCUMENTATION = "documentation"
    MIXED = "mixed"
    UNKNOWN = "unknown"
