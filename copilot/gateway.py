"""Local-first model gateway with protocol fallback and telemetry."""
from __future__ import annotations

import base64
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ModelUnavailable(RuntimeError):
    """Raised when a configured model backend cannot serve a request."""


class GatewayConfigurationError(ModelUnavailable):
    """Raised when required backend configuration is missing."""


@dataclass(frozen=True)
class GatewayResponse:
    text: str
    tool_calls: List[Dict[str, Any]]
    usage: Dict[str, int]
    latency_ms: float
    model_id: str
    backend: str
    bytes_off_device: int

    def as_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "tool_calls": self.tool_calls,
            "usage": self.usage,
            "latency_ms": self.latency_ms,
            "model_id": self.model_id,
            "backend": self.backend,
            "bytes_off_device": self.bytes_off_device,
        }


@dataclass
class Capabilities:
    supports_images: bool = False
    supports_tool_calling: bool = False
    supports_json_schema: bool = False
    backend: str = "LOCAL"
    model_id: Optional[str] = None
    installed_models: List[str] = field(default_factory=list)
    available: bool = False
    error: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "supports_images": self.supports_images,
            "supports_tool_calling": self.supports_tool_calling,
            "supports_json_schema": self.supports_json_schema,
            "backend": self.backend,
            "model_id": self.model_id,
            "installed_models": self.installed_models,
            "available": self.available,
            "error": self.error,
        }


def _load_dotenv() -> None:
    path = Path(os.getenv("COPILOT_ENV_FILE", ".env"))
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        os.environ.setdefault(key, value)


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _tool_calls_from_message(message: Dict[str, Any]) -> List[Dict[str, Any]]:
    calls = []
    for call in message.get("tool_calls") or []:
        function = call.get("function", {})
        arguments = function.get("arguments", {})
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        calls.append({"name": function.get("name"), "arguments": arguments})
    return calls


class LocalBackend:
    name = "LOCAL"

    def __init__(self, base_url: str, api_key: str, timeout: float, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.model = model

    def _request(self, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(
            f"{self.base_url}{path}",
            data=None if payload is None else _json_bytes(payload),
            headers=headers,
            method="GET" if payload is None else "POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ModelUnavailable(f"LOCAL model endpoint unavailable at {self.base_url}: {exc}") from exc

    def list_models(self) -> List[str]:
        data = self._request("/models")
        models = data.get("data", data.get("models", []))
        return [
            item.get("id", item.get("name", "")) if isinstance(item, dict) else str(item)
            for item in models
        ]

    def generate(
        self,
        messages: List[Dict[str, Any]],
        images: Optional[List[bytes]],
        tools: Optional[List[Dict[str, Any]]],
        json_schema: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        normalized = []
        for message in messages:
            content = message.get("content")
            if images and message.get("role") == "user" and isinstance(content, str):
                content = [{"type": "text", "text": content}] + [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{base64.b64encode(image).decode()}"},
                    }
                    for image in images
                ]
            normalized.append({**message, "content": content})
        payload: Dict[str, Any] = {"model": self.model, "messages": normalized}
        if tools:
            payload.update({"tools": tools, "tool_choice": "auto"})
        if json_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": json_schema,
            }
        data = self._request("/chat/completions", payload)
        message = data["choices"][0]["message"]
        usage = data.get("usage", {})
        return {
            "text": message.get("content") or "",
            "tool_calls": _tool_calls_from_message(message),
            "usage": {
                "in": int(usage.get("prompt_tokens", 0)),
                "out": int(usage.get("completion_tokens", 0)),
            },
            "request_bytes": len(_json_bytes(payload)),
        }


class CloudBackend:
    """Optional Google GenAI backend loaded only when CLOUD is selected."""

    name = "CLOUD"

    def __init__(self, model: str, api_key: str, timeout: float):
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        try:
            from google import genai  # type: ignore
        except ImportError as exc:
            raise GatewayConfigurationError(
                "CLOUD requires the optional google-genai package; install it and set GEMMA_API_KEY"
            ) from exc
        self._genai = genai
        self.client = genai.Client(api_key=api_key)

    def list_models(self) -> List[str]:
        try:
            return [getattr(item, "name", str(item)) for item in self.client.models.list()]
        except Exception as exc:
            raise ModelUnavailable(f"CLOUD model listing failed: {exc}") from exc

    def generate(self, messages, images, tools, json_schema):
        try:
            contents = []
            for message in messages:
                parts = [message.get("content", "")]
                contents.append({"role": message.get("role", "user"), "parts": parts})
            config: Dict[str, Any] = {}
            if tools:
                declarations = []
                for item in tools:
                    function = item.get("function", item)
                    declarations.append({
                        "name": function["name"],
                        "description": function.get("description", ""),
                        "parameters": function.get("parameters", {"type": "object"}),
                    })
                config["tools"] = [{"function_declarations": declarations}]
            if json_schema:
                config["response_mime_type"] = "application/json"
                config["response_schema"] = json_schema.get("schema", json_schema)
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config or None,
            )
            usage = getattr(response, "usage_metadata", None)
            return {
                "text": getattr(response, "text", "") or "",
                "tool_calls": [],
                "usage": {
                    "in": int(getattr(usage, "prompt_token_count", 0) or 0),
                    "out": int(getattr(usage, "candidates_token_count", 0) or 0),
                },
                "request_bytes": len(_json_bytes(contents)),
            }
        except Exception as exc:
            raise ModelUnavailable(f"CLOUD generation failed: {exc}") from exc


class MockBackend:
    """Deterministic backend for routing, fallback, and telemetry tests."""

    name = "MOCK"

    def __init__(
        self,
        responses: Iterable[Dict[str, Any]],
        model: str = "mock-gemma",
        capabilities: Optional[Dict[str, bool]] = None,
        installed_models: Optional[List[str]] = None,
    ):
        self.responses = list(responses)
        self.model = model
        self.capabilities = capabilities or {
            "supports_images": True,
            "supports_tool_calling": True,
            "supports_json_schema": True,
        }
        self.installed_models = installed_models or [model]

    def list_models(self):
        return self.installed_models

    def generate(self, messages, images, tools, json_schema):
        if not self.responses:
            raise ModelUnavailable("MOCK has no canned response remaining")
        response = dict(self.responses.pop(0))
        response.setdefault("text", "")
        response.setdefault("tool_calls", [])
        response.setdefault("usage", {"in": 0, "out": 0})
        response["request_bytes"] = len(_json_bytes({
            "messages": messages, "images": images, "tools": tools, "json_schema": json_schema,
        }))
        return response


class ModelGateway:
    """Single model boundary for ForgeASM."""

    def __init__(
        self,
        backend: Optional[Any] = None,
        telemetry_path: Optional[str] = None,
        retry_backoff: float = 0.05,
    ):
        _load_dotenv()
        self.backend_name = os.getenv("GEMMA_BACKEND", "LOCAL").upper()
        self.timeout = float(os.getenv("GEMMA_TIMEOUT_SECONDS", "60"))
        self.retry_backoff = retry_backoff
        self.telemetry_path = Path(
            telemetry_path or os.getenv("COPILOT_TELEMETRY_PATH", "logs/copilot_telemetry.jsonl")
        )
        self._telemetry: List[Dict[str, Any]] = []
        self._lock = Lock()
        self.session_id = "default"
        self.capabilities = Capabilities(backend=self.backend_name)
        self.backend = backend or self._build_backend()
        self.capabilities.backend = getattr(self.backend, "name", self.backend_name)

    def _build_backend(self):
        model = os.getenv("GEMMA_FAST_MODEL")
        if not model:
            raise GatewayConfigurationError(
                "GEMMA_FAST_MODEL is missing. Set it to an installed local Gemma tag "
                "or configure GEMMA_BACKEND=CLOUD with GEMMA_API_KEY."
            )
        if self.backend_name == "CLOUD":
            return CloudBackend(model, os.getenv("GEMMA_API_KEY", ""), self.timeout)
        if self.backend_name != "LOCAL":
            raise GatewayConfigurationError("GEMMA_BACKEND must be LOCAL or CLOUD")
        return LocalBackend(
            os.getenv("GEMMA_BASE_URL", "http://127.0.0.1:11434/v1"),
            os.getenv("GEMMA_API_KEY", ""),
            self.timeout,
            model,
        )

    def startup_check(self) -> Capabilities:
        try:
            installed = self.backend.list_models()
            self.capabilities.installed_models = installed
            self.capabilities.model_id = self.backend.model
            fast_model = getattr(self.backend, "model", None)
            if fast_model and installed and not any(fast_model in item for item in installed):
                raise GatewayConfigurationError(
                    f"Configured GEMMA_FAST_MODEL='{fast_model}' is not installed. "
                    f"Installed models: {', '.join(installed) or '(none)'}"
                )
            probe = self.backend.generate(
                [{"role": "user", "content": "Reply with OK."}], None, None, None
            )
            self.capabilities.available = True
            declared = getattr(self.backend, "capabilities", {})
            self.capabilities.supports_images = self._probe_images(declared)
            self.capabilities.supports_tool_calling = self._probe_tools(declared)
            self.capabilities.supports_json_schema = self._probe_schema(declared)
            if probe.get("tool_calls"):
                self.capabilities.supports_tool_calling = True
        except ModelUnavailable as exc:
            self.capabilities.error = str(exc)
        return self.capabilities

    def _probe_images(self, declared: Dict[str, bool]) -> bool:
        if "supports_images" in declared:
            return bool(declared["supports_images"])
        try:
            self.backend.generate(
                [{"role": "user", "content": "Describe this image."}],
                [b"\x89PNG\r\n\x1a\n"],
                None,
                None,
            )
            return True
        except ModelUnavailable:
            return False

    def _probe_tools(self, declared: Dict[str, bool]) -> bool:
        if "supports_tool_calling" in declared:
            return bool(declared["supports_tool_calling"])
        try:
            response = self.backend.generate(
                [{"role": "user", "content": "Call ping."}],
                None,
                [{
                    "type": "function",
                    "function": {
                        "name": "ping",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }],
                None,
            )
            return bool(response.get("tool_calls"))
        except ModelUnavailable:
            return False

    def _probe_schema(self, declared: Dict[str, bool]) -> bool:
        if "supports_json_schema" in declared:
            return bool(declared["supports_json_schema"])
        try:
            self.backend.generate(
                [{"role": "user", "content": "Return JSON."}],
                None,
                None,
                {
                    "name": "probe",
                    "schema": {
                        "type": "object",
                        "properties": {"ok": {"type": "boolean"}},
                        "required": ["ok"],
                    },
                },
            )
            return True
        except ModelUnavailable:
            return False

    def _text_protocol_schema(self, tools: List[Dict[str, Any]]) -> Dict[str, Any]:
        names = [
            item.get("function", {}).get("name", item.get("name"))
            for item in tools
        ]
        return {
            "name": "tool_turn",
            "schema": {
                "type": "object",
                "properties": {
                    "tool": {"type": "string", "enum": names},
                    "args": {"type": "object"},
                },
                "required": ["tool", "args"],
                "additionalProperties": False,
            },
        }

    def generate(self, messages, images=None, tools=None, json_schema=None, tier="fast"):
        if tier not in ("fast", "heavy"):
            raise ValueError("tier must be 'fast' or 'heavy'")
        if tier == "heavy":
            heavy_model = os.getenv("GEMMA_HEAVY_MODEL")
            if heavy_model and hasattr(self.backend, "model"):
                self.backend.model = heavy_model
        effective_schema = json_schema
        if tools and not self.capabilities.supports_tool_calling:
            effective_schema = self._text_protocol_schema(tools)
        last_error: Optional[Exception] = None
        for attempt in range(2):
            started = time.perf_counter()
            try:
                raw = self.backend.generate(messages, images, tools if self.capabilities.supports_tool_calling else None, effective_schema)
                text = raw.get("text", "")
                calls = list(raw.get("tool_calls", []))
                if tools and not self.capabilities.supports_tool_calling:
                    try:
                        parsed = json.loads(text)
                        calls = [{"name": parsed["tool"], "arguments": parsed["args"]}]
                    except (TypeError, KeyError, json.JSONDecodeError) as exc:
                        raise ModelUnavailable(f"Text tool protocol returned invalid JSON: {exc}") from exc
                    self._validate_tool_call(calls[0], tools)
                latency_ms = (time.perf_counter() - started) * 1000
                usage = {"in": int(raw.get("usage", {}).get("in", 0)), "out": int(raw.get("usage", {}).get("out", 0))}
                result = GatewayResponse(
                    text=text, tool_calls=calls, usage=usage, latency_ms=latency_ms,
                    model_id=getattr(self.backend, "model", "mock"),
                    backend=getattr(self.backend, "name", self.backend_name),
                    bytes_off_device=0 if getattr(self.backend, "name", self.backend_name) == "LOCAL" else int(raw.get("request_bytes", 0)),
                )
                self._record(result, raw.get("request_bytes", 0))
                return result.as_dict()
            except ModelUnavailable as exc:
                last_error = exc
                if attempt == 0:
                    time.sleep(self.retry_backoff)
        raise ModelUnavailable(str(last_error)) from last_error

    def set_session_id(self, session_id: str) -> None:
        if not session_id or len(session_id) > 200:
            raise ValueError("session_id must be non-empty and at most 200 characters")
        self.session_id = session_id

    @staticmethod
    def _validate_tool_call(call: Dict[str, Any], tools: List[Dict[str, Any]]) -> None:
        definitions = {
            item.get("function", {}).get("name", item.get("name")): item
            for item in tools
        }
        name = call.get("name")
        if name not in definitions or not isinstance(call.get("arguments"), dict):
            raise ModelUnavailable("Text tool protocol referenced an invalid tool or args object")
        schema = definitions[name].get("function", {}).get("parameters", {})
        required = schema.get("required", [])
        arguments = call["arguments"]
        missing = [key for key in required if key not in arguments]
        if missing:
            raise ModelUnavailable(f"Text tool protocol is missing required args: {', '.join(missing)}")
        if schema.get("additionalProperties") is False:
            allowed = set(schema.get("properties", {}))
            unexpected = set(arguments) - allowed
            if unexpected:
                raise ModelUnavailable(
                    f"Text tool protocol has unexpected args: {', '.join(sorted(unexpected))}"
                )

    def _record(self, response: GatewayResponse, request_bytes: int) -> None:
        tokens = response.usage["in"] + response.usage["out"]
        entry = {
            "id": str(uuid.uuid4()),
            "session_id": self.session_id,
            "timestamp": time.time(),
            "backend": response.backend,
            "model_id": response.model_id,
            "tokens_in": response.usage["in"],
            "tokens_out": response.usage["out"],
            "latency_ms": response.latency_ms,
            "tokens_per_sec": tokens / (response.latency_ms / 1000) if response.latency_ms else 0,
            "bytes_off_device": response.bytes_off_device,
        }
        with self._lock:
            self._telemetry.append(entry)
            self.telemetry_path.parent.mkdir(parents=True, exist_ok=True)
            with self.telemetry_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry) + "\n")

    def telemetry(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._telemetry)

    def capabilities_snapshot(self) -> Dict[str, Any]:
        return self.capabilities.as_dict()
