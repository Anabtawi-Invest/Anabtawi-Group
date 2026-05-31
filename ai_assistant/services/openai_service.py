# -*- coding: utf-8 -*-

import json
import logging

from odoo import _

from .config import (
    get_openai_api_key,
    get_openai_model,
    is_ai_assistant_enabled,
)
from .exceptions import AiAssistantError
from .tool_definitions import OPENAI_TOOL_DEFINITIONS
from .tool_executor import AIToolExecutor

_logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Odoo AI Assistant, embedded in an Odoo ERP system.

You can query business data using the provided tools. Rules:
- Use list_models and get_model_fields when you are unsure about model or field names.
- Prefer search_count for "how many" questions.
- Prefer aggregate_records for totals, top-N, revenue, or grouped metrics.
- Prefer search_records for listing individual records.
- Odoo domains are JSON arrays, e.g. [["state","=","posted"]].
- Respect tool limits; if results are truncated, say so.
- Never invent record ids; search first.
- Answer in clear natural language for business users.
- Do not claim you ran actions you did not perform via tools.
"""

MAX_TOOL_ITERATIONS = 10
REQUEST_TIMEOUT = 90.0


class OpenAIService:
    """OpenAI Chat Completions provider with local Odoo tool execution."""

    def __init__(self, env):
        self.env = env
        self.tool_executor = AIToolExecutor(env)

    def is_enabled(self):
        return is_ai_assistant_enabled(self.env)

    def get_model(self):
        return get_openai_model(self.env)

    def chat(self, user_message, history=None):
        """Run OpenAI chat with tool loop; return {content, meta} like MockAIService."""
        self._validate_configuration()

        user_message = (user_message or "").strip()
        if not user_message:
            raise AiAssistantError(_("Message cannot be empty."), "empty_message")

        client = self._get_client()
        messages = self._build_messages(user_message, history)
        tool_calls_log = []

        for iteration in range(MAX_TOOL_ITERATIONS):
            try:
                response = client.chat.completions.create(
                    model=self.get_model(),
                    messages=messages,
                    tools=OPENAI_TOOL_DEFINITIONS,
                    tool_choice="auto",
                    timeout=REQUEST_TIMEOUT,
                )
            except Exception as exc:
                raise self._map_openai_exception(exc) from exc

            choice = response.choices[0] if response.choices else None
            if not choice or not choice.message:
                raise AiAssistantError(_("OpenAI returned an empty response."), "invalid_response")

            assistant_message = choice.message
            if assistant_message.tool_calls:
                messages.append(self._message_to_dict(assistant_message))
                for tool_call in assistant_message.tool_calls:
                    tool_output, log_entry = self._run_tool_call(tool_call)
                    tool_calls_log.append(log_entry)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(tool_output, default=str),
                    })
                continue

            content = (assistant_message.content or "").strip()
            if not content:
                raise AiAssistantError(_("OpenAI returned an empty message."), "invalid_response")

            usage = {}
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }

            return {
                "content": content,
                "meta": {
                    "provider": "openai",
                    "model": self.get_model(),
                    "tool_calls": tool_calls_log,
                    "iterations": iteration + 1,
                    "usage": usage,
                },
            }

        raise AiAssistantError(
            _("The assistant needed too many data lookups. Please narrow your question."),
            "tool_loop_limit",
        )

    def _validate_configuration(self):
        if not self.is_enabled():
            raise AiAssistantError(_("AI Assistant is disabled."), "disabled")
        if not get_openai_api_key(self.env):
            raise AiAssistantError(_("OpenAI API key is not configured."), "missing_api_key")

    def _get_client(self):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise AiAssistantError(
                _(
                    "OpenAI Python package is not installed for this Odoo process "
                    "(%(detail)s). Install with: %(python)s -m pip install 'openai>=1.40.0' "
                    "then restart the Odoo server.",
                    detail=exc,
                    python=__import__("sys").executable,
                ),
                "provider_unavailable",
            ) from exc

        return OpenAI(
            api_key=get_openai_api_key(self.env),
            timeout=REQUEST_TIMEOUT,
            max_retries=0,
        )

    def _build_messages(self, user_message, history):
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for entry in history or []:
            role = entry.get("role")
            content = (entry.get("content") or "").strip()
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_message})
        return messages

    def _run_tool_call(self, tool_call):
        fn = tool_call.function
        name = fn.name
        raw_args = fn.arguments or "{}"
        output = self.tool_executor.execute(name, raw_args)
        log_entry = {
            "tool": name,
            "arguments": raw_args,
            "result": output,
        }
        return output, log_entry

    def _message_to_dict(self, message):
        """Convert an OpenAI message object to a plain dict for the next request."""
        data = {
            "role": message.role,
            "content": message.content,
        }
        if message.tool_calls:
            data["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ]
        return data

    def _map_openai_exception(self, exc):
        try:
            from openai import (
                APIConnectionError,
                APITimeoutError,
                AuthenticationError,
                BadRequestError,
                OpenAIError,
                RateLimitError,
            )
        except ImportError:
            return AiAssistantError(str(exc), "provider_unavailable")

        if isinstance(exc, AuthenticationError):
            return AiAssistantError(
                _("Invalid OpenAI API key. Check the key in Settings."),
                "invalid_api_key",
            )
        if isinstance(exc, RateLimitError):
            return AiAssistantError(
                _("OpenAI rate limit reached. Please try again later."),
                "rate_limit",
            )
        if isinstance(exc, APITimeoutError):
            return AiAssistantError(
                _("OpenAI request timed out. Please try again."),
                "timeout",
            )
        if isinstance(exc, APIConnectionError):
            return AiAssistantError(
                _("Could not connect to OpenAI. Check your network and try again."),
                "connection_error",
            )
        if isinstance(exc, BadRequestError):
            return AiAssistantError(
                _("OpenAI rejected the request: %(msg)s", msg=str(exc)),
                "api_error",
            )
        if isinstance(exc, OpenAIError):
            return AiAssistantError(
                _("OpenAI error: %(msg)s", msg=str(exc)),
                "api_error",
            )
        return AiAssistantError(
            _("An unexpected error occurred while calling OpenAI."),
            "provider_unavailable",
        )
