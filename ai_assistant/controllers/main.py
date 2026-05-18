# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request

from odoo.addons.ai_assistant.services.ai_assistant_service import (
    get_active_provider_name,
    get_ai_assistant_service,
)
from odoo.addons.ai_assistant.services.exceptions import AiAssistantError


class AiAssistantController(http.Controller):

    @http.route("/ai_assistant/status", type="jsonrpc", auth="user")
    def status(self):
        from odoo.addons.ai_assistant.services.config import is_ai_assistant_enabled

        return {
            "enabled": is_ai_assistant_enabled(request.env),
            "provider": get_active_provider_name(request.env),
        }

    @http.route("/ai_assistant/chat", type="jsonrpc", auth="user")
    def chat(self, message, history=None):
        """Return an assistant reply for a user message (stateless, no DB)."""
        service = get_ai_assistant_service(request.env)
        try:
            result = service.chat(message, history=history)
            return {
                "success": True,
                "content": result["content"],
                "meta": result.get("meta", {}),
            }
        except AiAssistantError as exc:
            return {
                "success": False,
                "error": str(exc),
                "error_code": exc.error_code,
            }
        except Exception:
            return {
                "success": False,
                "error": "An unexpected error occurred. Please try again.",
                "error_code": "server_error",
            }
