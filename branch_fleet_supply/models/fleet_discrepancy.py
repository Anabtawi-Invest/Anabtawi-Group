# -*- coding: utf-8 -*-
from odoo import fields, models

class FleetDiscrepancy(models.Model):
    _name = "fleet.discrepancy.case"
    _description = "Fleet Transit Discrepancy Case"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default="New", readonly=True, copy=False, tracking=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)

    order_id = fields.Many2one("branch.supply.order", readonly=True, index=True, ondelete="cascade")
    line_id = fields.Many2one("branch.supply.line", readonly=True, index=True, ondelete="set null")

    product_id = fields.Many2one("product.product", readonly=True, index=True)
    uom_id = fields.Many2one("uom.uom", readonly=True)
    missing_qty = fields.Float(readonly=True)

    state = fields.Selection([
        ("open", "Open"),
        ("reviewed", "Reviewed"),
        ("closed", "Closed"),
        ("cancel", "Cancelled"),
    ], default="open", tracking=True)

    resolution_type = fields.Selection([
        ("damage", "Damaged"),
        ("lost", "Lost In Transit"),
        ("miscount", "Miscount"),
        ("found", "Found Later"),
        ("other", "Other"),
    ], tracking=True)

    responsible_partner_id = fields.Many2one("res.partner", string="Responsible (Internal/Carrier)", tracking=True)
    notes = fields.Text()

    def action_mark_reviewed(self):
        self.write({"state": "reviewed"})

    def action_close(self):
        self.write({"state": "closed"})

    def action_cancel(self):
        self.write({"state": "cancel"})
