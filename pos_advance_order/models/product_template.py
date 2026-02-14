# -*- coding: utf-8 -*-

from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    has_pledge = fields.Boolean(string="Has Pledge")
    pledge_currency_id = fields.Many2one(
        "res.currency",
        compute="_compute_pledge_currency_id",
        readonly=True,
    )
    pledge_amount = fields.Monetary(
        string="Pledge Amount",
        currency_field="pledge_currency_id",
        default=0.0,
    )

    @api.depends("company_id")
    def _compute_pledge_currency_id(self):
        for rec in self:
            rec.pledge_currency_id = (rec.company_id or self.env.company).currency_id

