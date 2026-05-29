"""Anthropic Messages API schemas for /v1/messages (Claude Code / VS Code)."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AnthropicMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: Literal["user", "assistant", "system"]
    content: str | list[dict[str, Any]] | None = None


class AnthropicMessagesRequest(BaseModel):
    """Subset of Anthropic POST /v1/messages — extra fields forwarded as ignored."""

    model_config = ConfigDict(extra="allow")

    model: str
    max_tokens: int = Field(ge=1)
    messages: list[AnthropicMessage] = Field(min_length=1)
    system: str | list[dict[str, Any]] | None = None
    stream: bool = False
    temperature: float | None = Field(default=None, ge=0, le=1)
    top_p: float | None = None
    metadata: dict[str, Any] | None = None


class AnthropicUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class AnthropicTextBlock(BaseModel):
    type: Literal["text"] = "text"
    text: str


class AnthropicMessageResponse(BaseModel):
    id: str
    type: Literal["message"] = "message"
    role: Literal["assistant"] = "assistant"
    content: list[AnthropicTextBlock]
    model: str
    stop_reason: str | None = "end_turn"
    stop_sequence: str | None = None
    usage: AnthropicUsage
