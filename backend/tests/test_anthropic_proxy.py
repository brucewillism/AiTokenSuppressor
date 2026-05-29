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


def test_anthropic_system_role_inside_messages_array():
    """Claude Code envia system dentro de messages[] — deve ir para bloco system."""
    req = AnthropicMessagesRequest(
        model="claude-3-5-sonnet-20241022",
        max_tokens=100,
        messages=[
            AnthropicMessage(role="user", content="Hi"),
            AnthropicMessage(role="system", content="You are Claude Code."),
            AnthropicMessage(role="assistant", content="Hello!"),
        ],
    )
    msgs = anthropic_request_to_messages(req)
    assert msgs[0].role.value == "system"
    assert "Claude Code" in msgs[0].content
    assert any(m.content == "Hi" for m in msgs)
