from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    enable_native_ask_ai_lma = fields.Boolean(config_parameter="ai_reporting.enable_native_ask_ai_lma", default=True)
    enable_advanced_report_chatbot = fields.Boolean(config_parameter="ai_reporting.enable_advanced_report_chatbot", default=True)
    native_ai_status = fields.Char(config_parameter="ai_reporting.native_ai_status", readonly=True)
    enable_local_memory = fields.Boolean(config_parameter="ai_reporting.enable_local_memory", default=True)
    enable_exact_cache = fields.Boolean(config_parameter="ai_reporting.enable_exact_cache", default=True)
    enable_parameterized_intents = fields.Boolean(config_parameter="ai_reporting.enable_parameterized_intents", default=True)
    enable_semantic_cache = fields.Boolean(config_parameter="ai_reporting.enable_semantic_cache", default=True)
    enable_local_embeddings = fields.Boolean(config_parameter="ai_reporting.enable_local_embeddings", default=False)
    enable_local_model = fields.Boolean(config_parameter="ai_reporting.enable_local_model", default=False)
    enable_external_fallback = fields.Boolean(config_parameter="ai_reporting.enable_external_fallback", default=True)
    third_party_provider = fields.Selection(
        [("none", "None"), ("openai", "OpenAI"), ("anthropic", "Claude / Anthropic")],
        config_parameter="ai_reporting.third_party_provider",
        default="none",
    )
    openai_api_key_env = fields.Char(config_parameter="ai_reporting.openai_api_key_env", default="OPENAI_API_KEY")
    openai_model = fields.Char(config_parameter="ai_reporting.openai_model", default="gpt-5.6-terra")
    anthropic_api_key_env = fields.Char(config_parameter="ai_reporting.anthropic_api_key_env", default="ANTHROPIC_API_KEY")
    anthropic_model = fields.Char(config_parameter="ai_reporting.anthropic_model", default="claude-sonnet-5")
    ai_provider_timeout = fields.Integer(config_parameter="ai_reporting.ai_provider_timeout", default=60)
    ai_provider_max_tokens = fields.Integer(config_parameter="ai_reporting.ai_provider_max_tokens", default=3000)
    semantic_auto_execute_threshold = fields.Float(config_parameter="ai_reporting.semantic_auto_execute_threshold", default=0.92)
    semantic_review_threshold = fields.Float(config_parameter="ai_reporting.semantic_review_threshold", default=0.75)
    maximum_report_records = fields.Integer(config_parameter="ai_reporting.maximum_report_records", default=50000)
    maximum_synchronous_records = fields.Integer(config_parameter="ai_reporting.maximum_synchronous_records", default=5000)
    maximum_groups = fields.Integer(config_parameter="ai_reporting.maximum_groups", default=200)
    maximum_date_range = fields.Integer(config_parameter="ai_reporting.maximum_date_range", default=366)
    metadata_refresh_frequency = fields.Integer(config_parameter="ai_reporting.metadata_refresh_frequency", default=24)
    memory_retention_days = fields.Integer(config_parameter="ai_reporting.memory_retention_days", default=365)
    enable_english = fields.Boolean(config_parameter="ai_reporting.enable_english", default=True)
    enable_arabic = fields.Boolean(config_parameter="ai_reporting.enable_arabic", default=True)
    enable_egyptian_aliases = fields.Boolean(config_parameter="ai_reporting.enable_egyptian_aliases", default=False)
    enable_gulf_aliases = fields.Boolean(config_parameter="ai_reporting.enable_gulf_aliases", default=False)
    require_memory_approval = fields.Boolean(config_parameter="ai_reporting.require_memory_approval", default=True)
    require_report_confirmation = fields.Boolean(config_parameter="ai_reporting.require_report_confirmation", default=True)
    enable_usage_tracking = fields.Boolean(config_parameter="ai_reporting.enable_usage_tracking", default=True)
    enable_detailed_audit_logging = fields.Boolean(config_parameter="ai_reporting.enable_detailed_audit_logging", default=False)
