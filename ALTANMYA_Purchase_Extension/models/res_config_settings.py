# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import email_normalize


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    purchase_approval_email_from = fields.Char(
        string="Purchase Approval Sender Email",
        config_parameter="altanmya_purchase.approval_email_from",
    )

    @api.constrains("purchase_approval_email_from")
    def _check_purchase_approval_email_from(self):
        for settings in self:
            value = (settings.purchase_approval_email_from or "").strip()
            if value and not email_normalize(value):
                raise ValidationError(_("Enter a valid purchase approval sender email."))
