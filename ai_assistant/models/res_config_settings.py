# -*- coding: utf-8 -*-

from odoo import fields, models

from odoo.addons.ai_assistant.services.config import (
    DEFAULT_OPENAI_MODEL,
    PROVIDER_MOCK,
    PROVIDER_OPENAI,
)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    ai_assistant_enabled = fields.Boolean(
        string="AI Assistant Enabled",
        config_parameter="ai_assistant.enabled",
        default=True,
    )
    ai_assistant_provider = fields.Selection(
        selection=[
            (PROVIDER_MOCK, "Mock (testing / fallback)"),
            (PROVIDER_OPENAI, "OpenAI (ChatGPT)"),
        ],
        string="AI Provider",
        config_parameter="ai_assistant.provider",
        default=PROVIDER_MOCK,
        required=True,
    )
    ai_assistant_openai_api_key = fields.Char(
        string="OpenAI API Key",
        config_parameter="ai_assistant.openai_api_key",
        help="Stored in system parameters. Required when AI Provider is OpenAI.",
    )
    ai_assistant_openai_model = fields.Char(
        string="OpenAI Model Name",
        config_parameter="ai_assistant.openai_model",
        default=DEFAULT_OPENAI_MODEL,
        help="Example: gpt-4o-mini, gpt-4o",
    )
