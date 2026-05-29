"""Tests for Anthropic /v1/messages conversion."""

from app.schemas.anthropic_proxy import AnthropicMessage, AnthropicMessagesRequest
from app.services.anthropic_proxy_service import anthropic_request_to_messages


def test_anthropic_system_and_user_messages():
    req = AnthropicMessagesRequest(
        model="claude-3-5-sonnet-20241022",
        max_tokens=100,
        system="You are helpful.",
        messages=[AnthropicMessage(role="user", content="Hello")],
    )
    msgs = anthropic_request_to_messages(req)
    assert len(msgs) == 2
    assert msgs[0].role.value == "system"
    assert msgs[1].content == "Hello"
