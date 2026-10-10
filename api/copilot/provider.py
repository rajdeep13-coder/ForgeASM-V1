"""Small OpenAI-compatible client used by the ForgeASM Copilot.

The client intentionally uses the standard library so the simulator remains
usable without adding a hosted-model SDK or requiring a cloud service.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ProviderConfigurationError(RuntimeError):
    """Raised when the local model provider is not configured."""


class ProviderRequestError(RuntimeError):
    """Raised when the model provider cannot complete a request."""


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: Dict[str, Any]


@dataclass(frozen=True)
class ModelResponse:
    content: str
    tool_calls: List[ToolCall]


class OpenAICompatibleProvider:
    """OpenAI Chat Completions compatible provider for local inference."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("GEMMA_BASE_URL", "http://127.0.0.1:11434/v1")).rstrip("/")
        self.model = model or os.getenv("GEMMA_MODEL")
        if not self.model:
            raise ProviderConfigurationError("GEMMA_MODEL is not configured")
        self.api_key = os.getenv("GEMMA_API_KEY", "")
        self.timeout = timeout or float(os.getenv("GEMMA_TIMEOUT_SECONDS", "60"))

    def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
    ) -> ModelResponse:
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise ProviderRequestError(f"Gemma provider request failed: {exc}") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderRequestError("Gemma provider returned invalid JSON") from exc

        try:
            message = data["choices"][0]["message"]
            content = message.get("content") or ""
            raw_calls = message.get("tool_calls") or []
            calls = [
                ToolCall(
                    name=call["function"]["name"],
                    arguments=json.loads(call["function"]["arguments"]),
                )
                for call in raw_calls
            ]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ProviderRequestError("Gemma provider returned an invalid response shape") from exc
        return ModelResponse(content=content, tool_calls=calls)

