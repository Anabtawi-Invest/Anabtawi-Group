from odoo import models, fields


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    # ── Enable / connection ──────────────────────────────────────────────────
    apex_enabled = fields.Boolean(
        string="Enable Apex ECR",
        help="Enable Apex ECR EFTPOS integration for this payment method.",
    )
    apex_service_url = fields.Char(
        string="Apex Service URL",
        help="Full URL of the ApexECR SOAP endpoint, e.g. http://localhost:9999/ApexECR/Service.asmx",
    )

    # ── Merchant / terminal credentials ─────────────────────────────────────
    apex_mid = fields.Char(
        string="Merchant ID (MID)",
        help="15-character Merchant ID provided by the acquirer.",
    )
    apex_tid = fields.Char(
        string="Terminal ID (TID)",
        help="8-character Terminal ID provided by the acquirer.",
    )
    apex_secure_key = fields.Char(
        string="Merchant Secure Key",
        help="32-character MerchantSecureKey for request authentication.",
    )
    apex_currency_code = fields.Char(
        string="ECR Currency Code",
        default="400",
        help="ISO 4217 numeric code: 400 = JOD, 840 = USD, etc.",
    )

    # ── Printer / receipt settings ───────────────────────────────────────────
    apex_printer_width = fields.Integer(
        string="Printer Width (chars)",
        default=40,
        help="Number of characters per receipt line sent to the EFTPOS printer.",
    )
    apex_enable_print_pos_receipt = fields.Selection(
        selection=[
            ("0", "None"),
            ("1", "Merchant Copy"),
            ("2", "Customer Copy"),
            ("3", "Both Copies"),
        ],
        string="Print POS Receipt",
        default="3",
        help="Controls whether the EFTPOS terminal prints a receipt.",
    )

    # ── Timing ───────────────────────────────────────────────────────────────
    apex_timeout = fields.Integer(
        string="Request Timeout (s)",
        default=90,
        help="Seconds to wait for a response from the Apex terminal.",
    )
