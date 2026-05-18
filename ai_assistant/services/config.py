# -*- coding: utf-8 -*-

from odoo.tools.misc import str2bool

PARAM_ENABLED = "ai_assistant.enabled"
PARAM_PROVIDER = "ai_assistant.provider"
PARAM_OPENAI_API_KEY = "ai_assistant.openai_api_key"
PARAM_OPENAI_MODEL = "ai_assistant.openai_model"

PROVIDER_MOCK = "mock"
PROVIDER_OPENAI = "openai"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


def _icp(env):
    return env["ir.config_parameter"].sudo()


def is_ai_assistant_enabled(env):
    """Return whether the AI assistant is enabled in system parameters."""
    value = _icp(env).get_param(PARAM_ENABLED)
    if value is False or value is None:
        return False
    return str2bool(str(value))


def get_ai_provider(env):
    """Return the configured AI provider key (mock or openai)."""
    provider = _icp(env).get_param(PARAM_PROVIDER) or PROVIDER_MOCK
    if provider not in (PROVIDER_MOCK, PROVIDER_OPENAI):
        return PROVIDER_MOCK
    return provider


def get_openai_api_key(env):
    return _icp(env).get_param(PARAM_OPENAI_API_KEY) or ""


def get_openai_model(env):
    return _icp(env).get_param(PARAM_OPENAI_MODEL) or DEFAULT_OPENAI_MODEL
