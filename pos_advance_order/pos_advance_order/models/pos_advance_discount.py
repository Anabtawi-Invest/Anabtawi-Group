# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.fields import Domain
from odoo.exceptions import UserError
from odoo.fields import Command

class PosAdvanceDiscount(models.Model):
    _name = "pos.advance.discount"
    _description = "POS Advance Allowed Discounts"
    _order = "sequence, id"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)

    discount_type = fields.Selection(
        [
            ("percent", "Percentage"),
            ("amount", "Fixed Amount"),
        ],
        required=True,
        default="percent",
    )

    value = fields.Float(required=True)
    active = fields.Boolean(default=True)

    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
        required=True,
    )

    @api.constrains("discount_type", "value")
    def _check_discount_value(self):
        for rec in self:
            if rec.value <= 0:
                raise UserError(_("Discount value must be greater than zero."))
            if rec.discount_type == "percent" and rec.value > 100:
                raise UserError(_("Percentage discount cannot be greater than 100."))
