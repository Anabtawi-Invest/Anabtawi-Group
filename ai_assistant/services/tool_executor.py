# -*- coding: utf-8 -*-

import json
import logging
from datetime import date, datetime

from odoo import fields

from .ai_tools import OdooAITools
from .exceptions import AiAssistantError

_logger = logging.getLogger(__name__)

_TOOL_METHODS = frozenset({
    "list_models",
    "get_model_fields",
    "search_records",
    "read_records",
    "search_count",
    "aggregate_records",
})


class AIToolExecutor:
    """Dispatch OpenAI tool calls to generic OdooAITools methods."""

    def __init__(self, env):
        self.tools = OdooAITools(env)

    def execute(self, tool_name, arguments):
        """Run a tool and return a JSON-serializable result or error dict."""
        if tool_name not in _TOOL_METHODS:
            return {
                "error": "unknown_tool",
                "message": f"Unknown tool: {tool_name}",
            }

        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError as exc:
                _logger.warning("Malformed tool arguments for %s: %s", tool_name, arguments)
                return {
                    "error": "malformed_tool_args",
                    "message": str(exc),
                }

        if not isinstance(arguments, dict):
            return {
                "error": "malformed_tool_args",
                "message": "Tool arguments must be a JSON object.",
            }

        try:
            result = getattr(self.tools, tool_name)(**arguments)
            return {"ok": True, "result": self._serialize(result)}
        except AiAssistantError as exc:
            return {
                "error": exc.error_code,
                "message": str(exc),
            }
        except TypeError as exc:
            return {
                "error": "invalid_tool_args",
                "message": str(exc),
            }
        except Exception as exc:  # noqa: BLE001 — return safe error to the model
            _logger.exception("Tool %s failed", tool_name)
            return {
                "error": "tool_execution_error",
                "message": str(exc),
            }

    def _serialize(self, value):
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, (datetime, date)):
            return fields.Datetime.to_string(value) if isinstance(value, datetime) else fields.Date.to_string(value)
        if isinstance(value, dict):
            return {k: self._serialize(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._serialize(item) for item in value]
        return str(value)
