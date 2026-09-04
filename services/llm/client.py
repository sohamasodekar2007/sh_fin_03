"""
Thin, provider-agnostic LLM client wrapping the official `openai` Python
SDK — never hand-rolled HTTP. `base_url` is always passed through
explicitly, so this same client works talking directly to
https://api.openai.com/v1 or through an OpenAI-compatible proxy, with
whichever key belongs to that endpoint (see apps/api/.env.example).

Shared by the Decision agent (this phase) and the chatbot (Phase 7) — one
client, one retry policy, one place every call gets logged.

Never crashes the pipeline: on missing credentials or exhausted retries,
this raises LLMUnavailable, and every caller in this codebase is expected
to catch it and degrade to its deterministic path rather than let it
propagate.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from apps.api.config import Settings, get_settings
from apps.api.db import get_db

logger = logging.getLogger(__name__)

# HTTP status codes worth retrying: rate limits and server-side failures.
# 4xx client errors other than 429 (bad request, auth failure, etc) are not
# retryable — retrying an invalid request just burns the retry budget.
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class LLMUnavailable(Exception):
    """Raised when the LLM API key isn't configured, or every retry
    attempt failed. Callers must catch this and fall back to their
    deterministic path — it must never crash the pipeline."""


class LLMClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def _build_sdk_client(self):
        from openai import AsyncOpenAI

        return AsyncOpenAI(
            api_key=self.settings.openai_api_key,
            base_url=self.settings.openai_base_url,
        )

    async def complete(
        self,
        system: str,
        user: str,
        json_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Sends one chat completion request and returns the parsed JSON
        response body. Retries on 429/5xx with exponential backoff (max
        LLM_MAX_RETRIES attempts total), under a LLM_TIMEOUT_SECONDS hard
        timeout per attempt. Raises LLMUnavailable if the API key is
        missing or every attempt fails — never returns a partial/garbage
        result.
        """
        if not self.settings.openai_api_key:
            raise LLMUnavailable("OPENAI_API_KEY is not configured")

        sdk_client = self._build_sdk_client()
        prompt_hash = hashlib.sha256(f"{system}\n{user}".encode("utf-8")).hexdigest()[:16]

        response_format: dict[str, Any] = (
            {"type": "json_schema", "json_schema": json_schema} if json_schema else {"type": "json_object"}
        )

        max_retries = max(self.settings.llm_max_retries, 1)
        last_error: Exception | None = None

        for attempt in range(1, max_retries + 1):
            started_at = time.monotonic()
            try:
                response = await sdk_client.chat.completions.create(
                    model=self.settings.openai_model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format=response_format,
                    timeout=self.settings.llm_timeout_seconds,
                )
                latency_ms = int((time.monotonic() - started_at) * 1000)

                content = response.choices[0].message.content or "{}"
                parsed = _parse_json_response(content)

                usage = getattr(response, "usage", None)
                await self._log_call(
                    prompt_hash=prompt_hash,
                    model=self.settings.openai_model,
                    status="success",
                    attempt=attempt,
                    latency_ms=latency_ms,
                    input_tokens=getattr(usage, "prompt_tokens", None),
                    output_tokens=getattr(usage, "completion_tokens", None),
                    error=None,
                )
                return parsed

            except Exception as exc:  # noqa: BLE001 - any failure here must degrade, not crash
                last_error = exc
                latency_ms = int((time.monotonic() - started_at) * 1000)
                status_code = getattr(exc, "status_code", None)
                retryable = (status_code in _RETRYABLE_STATUS_CODES) if status_code is not None else True

                await self._log_call(
                    prompt_hash=prompt_hash,
                    model=self.settings.openai_model,
                    status="error",
                    attempt=attempt,
                    latency_ms=latency_ms,
                    input_tokens=None,
                    output_tokens=None,
                    error=str(exc)[:300],
                )

                if not retryable or attempt >= max_retries:
                    break

                backoff_seconds = 2 ** (attempt - 1)
                await asyncio.sleep(backoff_seconds)

        raise LLMUnavailable(f"LLM call failed after {max_retries} attempt(s): {last_error}") from last_error

    async def complete_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str | dict[str, Any] = "auto",
    ) -> dict[str, Any]:
        """
        OpenAI-style function/tool calling (the chatbot's tool round-trip,
        Phase 7) — a second request shape on the SAME client, SAME retry/
        timeout/logging policy as complete(), not a second LLM client.

        Returns {"content": str | None, "tool_calls": [{"id", "name",
        "arguments": dict}, ...]} — arguments are already JSON-parsed, so
        callers never touch a raw string. `messages` is the full OpenAI
        chat message list (system/user/assistant/tool) built by the
        caller — this method is stateless, like complete().
        """
        if not self.settings.openai_api_key:
            raise LLMUnavailable("OPENAI_API_KEY is not configured")

        sdk_client = self._build_sdk_client()
        prompt_hash = hashlib.sha256(json.dumps(messages, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]

        max_retries = max(self.settings.llm_max_retries, 1)
        last_error: Exception | None = None

        for attempt in range(1, max_retries + 1):
            started_at = time.monotonic()
            try:
                response = await sdk_client.chat.completions.create(
                    model=self.settings.openai_model,
                    messages=messages,
                    tools=tools,
                    tool_choice=tool_choice,
                    timeout=self.settings.llm_timeout_seconds,
                )
                latency_ms = int((time.monotonic() - started_at) * 1000)
                message = response.choices[0].message

                tool_calls: list[dict[str, Any]] = []
                for tc in message.tool_calls or []:
                    try:
                        arguments = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        arguments = {}
                    tool_calls.append({"id": tc.id, "name": tc.function.name, "arguments": arguments})

                usage = getattr(response, "usage", None)
                await self._log_call(
                    prompt_hash=prompt_hash,
                    model=self.settings.openai_model,
                    status="success",
                    attempt=attempt,
                    latency_ms=latency_ms,
                    input_tokens=getattr(usage, "prompt_tokens", None),
                    output_tokens=getattr(usage, "completion_tokens", None),
                    error=None,
                )
                return {"content": message.content, "tool_calls": tool_calls}

            except Exception as exc:  # noqa: BLE001 - any failure here must degrade, not crash
                last_error = exc
                latency_ms = int((time.monotonic() - started_at) * 1000)
                status_code = getattr(exc, "status_code", None)
                retryable = (status_code in _RETRYABLE_STATUS_CODES) if status_code is not None else True

                await self._log_call(
                    prompt_hash=prompt_hash,
                    model=self.settings.openai_model,
                    status="error",
                    attempt=attempt,
                    latency_ms=latency_ms,
                    input_tokens=None,
                    output_tokens=None,
                    error=str(exc)[:300],
                )

                if not retryable or attempt >= max_retries:
                    break

                backoff_seconds = 2 ** (attempt - 1)
                await asyncio.sleep(backoff_seconds)

        raise LLMUnavailable(f"LLM tool call failed after {max_retries} attempt(s): {last_error}") from last_error

    async def _log_call(
        self,
        *,
        prompt_hash: str,
        model: str,
        status: str,
        attempt: int,
        latency_ms: int,
        input_tokens: int | None,
        output_tokens: int | None,
        error: str | None,
    ) -> None:
        # Logged fields are metadata only — prompt_hash, never the prompt
        # itself, and certainly never the API key.
        try:
            db = get_db()
            await db.llm_calls.insert_one(
                {
                    "logged_at": datetime.now(timezone.utc),
                    "model": model,
                    "prompt_hash": prompt_hash,
                    "status": status,
                    "attempt": attempt,
                    "latency_ms": latency_ms,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "error": error,
                }
            )
        except Exception as log_err:  # noqa: BLE001 - logging must never break the LLM call itself
            logger.warning("llm.client: failed to log call: %s", log_err)


def _parse_json_response(content: str) -> dict[str, Any]:
    """Strips ```json / ``` markdown fences before parsing — some models
    wrap JSON-mode output in a fenced code block despite json_object mode
    asking for raw JSON."""
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)
