# -*- coding: utf-8 -*-

from odoo import api, fields, models


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    def _get_payment_terminal_selection(self):
        return super()._get_payment_terminal_selection() + [("apexecr", "ApexECR (SOAP)")]

    apexecr_endpoint_url = fields.Char(
        string="ApexECR Endpoint URL",
        default="http://127.0.0.1:18080/apexecrmock",
        help="SOAP endpoint URL (mock or real ApexECR service URL).",
        copy=False,
    )
    apexecr_mid = fields.Char(string="Apex MID", copy=False)
    apexecr_tid = fields.Char(string="Apex TID", copy=False)
    apexecr_merchant_secure_key = fields.Char(string="Apex Merchant Secure Key", copy=False)
    apexecr_currency_code = fields.Char(string="ECR Currency Code", default="400", copy=False)
    apexecr_tiller_username = fields.Char(string="Default Tiller Username", copy=False)
    apexecr_tiller_full_name = fields.Char(string="Default Tiller Full Name", copy=False)
    apexecr_timeout_sec = fields.Integer(string="SOAP Timeout (Seconds)", default=45, copy=False)
    apexecr_retry_count = fields.Integer(string="Retry Count", default=1, copy=False)
    apexecr_enable_print_pos_receipt = fields.Integer(
        string="Print EFTPOS Receipt",
        default=0,
        help="0 none, 1 merchant, 2 customer, 3 both",
        copy=False,
    )
    apexecr_enable_print_receipt_note = fields.Integer(
        string="Print Receipt Note Position",
        default=0,
        help="0 none, 1 before header, 2 after header, 3 before footer, 4 after footer",
        copy=False,
    )

    @api.model
    def _load_pos_data_fields(self, config):
        params = super()._load_pos_data_fields(config)
        params += [
            "apexecr_endpoint_url",
            "apexecr_mid",
            "apexecr_tid",
            "apexecr_currency_code",
            "apexecr_tiller_username",
            "apexecr_tiller_full_name",
            "apexecr_timeout_sec",
            "apexecr_retry_count",
            "apexecr_enable_print_pos_receipt",
            "apexecr_enable_print_receipt_note",
        ]
        return params

