# -*- coding: utf-8 -*-

from odoo import fields, models


class ApexEcrLog(models.Model):
    _name = "apexecr.log"
    _description = "ApexECR Integration Log"
    _order = "id desc"

    payment_method_id = fields.Many2one("pos.payment.method", string="POS Payment Method", ondelete="set null")
    reference_number = fields.Char(string="Reference Number", index=True)
    operation = fields.Char(string="Operation", required=True)
    request_payload = fields.Text(string="Request Payload")
    response_payload = fields.Text(string="Response Payload")
    status = fields.Selection(
        selection=[("ok", "OK"), ("error", "Error")],
        string="Status",
        default="ok",
        required=True,
    )
    error_message = fields.Char(string="Error Message")

