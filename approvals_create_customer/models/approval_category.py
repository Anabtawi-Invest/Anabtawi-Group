# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ApprovalCategory(models.Model):
    _inherit = "approval.category"

    approval_type = fields.Selection(
        selection_add=[("create_customer", "Create Customer")],
        ondelete={"create_customer": "set null"},
    )

    @api.onchange("approval_type")
    def _onchange_approval_type_create_customer(self):
        if self.approval_type == "create_customer":
            self.has_partner = "no"
            self.has_product = "no"
            self.has_quantity = "no"
            self.has_amount = "no"
            self.has_date = "no"
            self.has_period = "no"
            self.has_location = "no"
            self.has_reference = "no"
            self.has_payment_method = "no"
            self.requirer_document = "optional"
