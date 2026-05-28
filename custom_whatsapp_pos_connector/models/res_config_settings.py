from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    whatsapp_provider = fields.Selection(
        [("meta", "Meta Cloud API"), ("twilio", "Twilio WhatsApp")],
        string="WhatsApp Provider",
        config_parameter="custom_whatsapp_pos_connector.provider",
        default="meta",
        required=True,
    )
    whatsapp_meta_phone_number_id = fields.Char(
        string="Meta Phone Number ID",
        config_parameter="custom_whatsapp_pos_connector.meta_phone_number_id",
    )
    whatsapp_meta_access_token = fields.Char(
        string="Meta Access Token",
        config_parameter="custom_whatsapp_pos_connector.meta_access_token",
    )
    whatsapp_meta_verify_token = fields.Char(
        string="Webhook Verify Token",
        config_parameter="custom_whatsapp_pos_connector.meta_verify_token",
    )
    whatsapp_meta_business_account_id = fields.Char(
        string="Meta Business Account ID",
        config_parameter="custom_whatsapp_pos_connector.meta_business_account_id",
    )
    whatsapp_default_pos_config_id = fields.Many2one(
        "pos.config",
        string="Default POS Config for WhatsApp Orders",
        config_parameter="custom_whatsapp_pos_connector.default_pos_config_id",
    )
    whatsapp_webhook_enabled = fields.Boolean(
        string="Enable WhatsApp Webhook Processing",
        config_parameter="custom_whatsapp_pos_connector.webhook_enabled",
        default=True,
    )
    whatsapp_twilio_account_sid = fields.Char(
        string="Twilio Account SID",
        config_parameter="custom_whatsapp_pos_connector.twilio_account_sid",
    )
    whatsapp_twilio_auth_token = fields.Char(
        string="Twilio Auth Token",
        config_parameter="custom_whatsapp_pos_connector.twilio_auth_token",
    )
    whatsapp_twilio_whatsapp_from = fields.Char(
        string="Twilio WhatsApp From",
        config_parameter="custom_whatsapp_pos_connector.twilio_whatsapp_from",
        help="Example: whatsapp:+14155238886",
    )
