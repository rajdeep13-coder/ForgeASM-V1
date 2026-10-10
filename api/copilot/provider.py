"""Backward-compatible aliases for the centralized model gateway.

Model transport lives exclusively in :mod:`copilot.gateway`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from copilot.gateway import (
    GatewayConfigurationError as ProviderConfigurationError,
    ModelGateway,
    ModelUnavailable as ProviderRequestError,
)


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: Dict[str, Any]


@dataclass(frozen=True)
class ModelResponse:
    content: str
    tool_calls: List[ToolCall]


class OpenAICompatibleProvider:
    """Compatibility adapter for older agent callers."""

    def __init__(self, gateway: ModelGateway | None = None):
        self.gateway = gateway or ModelGateway()

    def complete(self, messages, tools):
        response = self.gateway.generate(messages, tools=tools)
        return ModelResponse(
            content=response["text"],
            tool_calls=[
                ToolCall(call["name"], call["arguments"])
                for call in response["tool_calls"]
            ],
        )
