"""
title: Holmes SRE Agent
author: Codex
version: 0.1.0
required_open_webui_version: 0.5.0
license: MIT
"""

import asyncio
import json
import time
import urllib.error
import urllib.request
import uuid
from typing import Iterable

try:
    from pydantic import BaseModel, Field
except ImportError:
    class BaseModel:
        def __init__(self, **kwargs):
            for name, value in self.__class__.__dict__.items():
                if name.startswith("_") or callable(value):
                    continue
                setattr(self, name, kwargs.get(name, value))

    def Field(default=None, description=""):
        del description
        return default


class Pipe:
    class Valves(BaseModel):
        HOLMES_API_BASE_URL: str = Field(
            default="http://holmesgpt-holmes.holmesgpt.svc:80",
            description="Base URL of the HolmesGPT service.",
        )
        MODEL_NAME: str = Field(
            default="Holmes SRE Agent",
            description="Model name shown in the Open WebUI selector.",
        )
        REQUEST_TIMEOUT_SECONDS: int = Field(
            default=600,
            description="Timeout for HolmesGPT requests.",
        )
        MAX_HISTORY_MESSAGES: int = Field(
            default=12,
            description="Maximum number of prior chat messages to forward as conversation history.",
        )
        INCLUDE_SYSTEM_MESSAGES: bool = Field(
            default=True,
            description="Fold Open WebUI system messages into the Holmes ask payload.",
        )
        SHOW_TOOL_CALLS: bool = Field(
            default=True,
            description="Append executed Holmes tool calls to the final answer.",
        )
        SHOW_RUNBOOKS: bool = Field(
            default=False,
            description="Append matched runbook instructions to the final answer.",
        )

    def __init__(self):
        self.valves = self.Valves()
        self._model_id = "holmes_sre_agent"

    def _kb_hint(self, ask: str) -> str:
        lowered = ask.lower()
        kb_markers = (
            "artifact key",
            "artifact keys",
            "s3 key",
            "source_key",
            "kubescape artifact",
            "k8sgpt artifact",
            "popeye artifact",
            "hub",
            "spoke-a",
            "spoke-b",
            "qdrant",
            "knowledge base",
            "kb ",
            "raw/",
        )
        if not any(marker in lowered for marker in kb_markers):
            return ask
        return (
            "Knowledge-base retrieval rule:\n"
            "For requests about artifact keys, stored findings, hub/spoke cluster results, or knowledge-base contents, "
            "use the kb/stack toolset first.\n"
            "Prefer kb_search and kb_fetch over kubectl-based investigation unless the user explicitly asks for live cluster state.\n\n"
            f"{ask}"
        )

    def pipes(self):
        return [{"id": self._model_id, "name": self.valves.MODEL_NAME}]

    def _extract_text(self, content) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str) and item.strip():
                    parts.append(item.strip())
                    continue
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text" and item.get("text"):
                    parts.append(str(item["text"]).strip())
                    continue
                if item.get("content"):
                    parts.append(str(item["content"]).strip())
            return "\n".join(part for part in parts if part)
        if content is None:
            return ""
        return str(content).strip()

    def _prepare_payload(self, body: dict) -> dict:
        messages = body.get("messages", [])
        if not isinstance(messages, list):
            raise ValueError("Open WebUI request body must contain a messages list.")

        system_messages = []
        conversation_history = []
        user_messages = []

        for message in messages:
            if not isinstance(message, dict):
                continue
            role = message.get("role", "user")
            text = self._extract_text(message.get("content"))
            if not text:
                continue
            if role == "system":
                system_messages.append(text)
                continue
            if role not in ("user", "assistant"):
                continue
            conversation_history.append({"role": role, "content": text})
            if role == "user":
                user_messages.append(text)

        if not user_messages:
            raise ValueError("No user message found in the Open WebUI request.")

        ask = user_messages[-1]
        history = conversation_history[:-1]
        max_history = max(int(self.valves.MAX_HISTORY_MESSAGES), 0)
        history = history[-max_history:] if max_history else []

        if self.valves.INCLUDE_SYSTEM_MESSAGES and system_messages:
            ask = (
                "Additional chat instructions from Open WebUI system messages:\n"
                + "\n\n".join(system_messages)
                + "\n\nCurrent user request:\n"
                + ask
            )

        ask = self._kb_hint(ask)

        payload = {"ask": ask}
        if history:
            payload["conversation_history"] = history
        return payload

    def _render_text(self, result: dict) -> str:
        analysis = (result.get("analysis") or "").strip()
        sections = [analysis or "HolmesGPT returned an empty analysis."]

        instructions = result.get("instructions") or []
        if self.valves.SHOW_RUNBOOKS and instructions:
            rendered = "\n".join(f"- {item}" for item in instructions if item)
            if rendered:
                sections.append("Matched runbooks:\n" + rendered)

        tool_calls = result.get("tool_calls") or []
        if self.valves.SHOW_TOOL_CALLS and tool_calls:
            lines = []
            for call in tool_calls:
                if not isinstance(call, dict):
                    continue
                name = call.get("function_name", "unknown")
                args = call.get("arguments", "")
                suffix = f" {args}" if args else ""
                lines.append(f"- {name}{suffix}")
            if lines:
                sections.append("Executed tools:\n" + "\n".join(lines))

        return "\n\n".join(section for section in sections if section).strip()

    def _request_holmes(self, payload: dict) -> dict:
        req = urllib.request.Request(
            f"{self.valves.HOLMES_API_BASE_URL.rstrip('/')}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        timeout = int(self.valves.REQUEST_TIMEOUT_SECONDS)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise RuntimeError(f"HolmesGPT returned HTTP {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Failed to reach HolmesGPT: {exc.reason}") from exc

    def _completion_response(self, text: str) -> dict:
        created = int(time.time())
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": created,
            "model": self._model_id,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
        }

    def _stream_response(self, text: str) -> Iterable[bytes]:
        created = int(time.time())
        response_id = f"chatcmpl-{uuid.uuid4().hex}"
        chunks = [text[i : i + 180] for i in range(0, len(text), 180)] or [""]
        first = True
        for chunk in chunks:
            delta = {"content": chunk}
            if first:
                delta = {"role": "assistant", "content": chunk}
                first = False
            payload = {
                "id": response_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": self._model_id,
                "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
            }
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")

        payload = {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": self._model_id,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")
        yield b"data: [DONE]\n\n"

    async def pipe(self, body: dict, __user__: dict = None, __request__=None):
        del __user__, __request__
        payload = self._prepare_payload(body)
        result = await asyncio.to_thread(self._request_holmes, payload)
        text = self._render_text(result)
        if body.get("stream", False):
            return self._stream_response(text)
        return self._completion_response(text)
