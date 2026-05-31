# -*- coding: utf-8 -*-

import logging

from odoo import _

from .config import PROVIDER_MOCK, PROVIDER_OPENAI, get_ai_provider
from .exceptions import AiAssistantError
from .mock_ai_service import MockAIService

_logger = logging.getLogger(__name__)


def get_ai_assistant_service(env):
    """Return the active AI assistant service based on system settings."""
    provider = get_ai_provider(env)
    if provider == PROVIDER_OPENAI:
        try:
            from .openai_service import OpenAIService

            return OpenAIService(env)
        except ImportError as exc:
            _logger.exception("OpenAI provider unavailable: %s", exc)
            raise AiAssistantError(
                _(
                    "OpenAI provider failed to load (%(detail)s). "
                    "Install openai in Odoo's Python environment and restart the server.",
                    detail=exc,
                ),
                "provider_unavailable",
            ) from exc
    return MockAIService(env)


def get_active_provider_name(env):
    """Return the configured provider key without instantiating OpenAI."""
    return get_ai_provider(env) or PROVIDER_MOCK
