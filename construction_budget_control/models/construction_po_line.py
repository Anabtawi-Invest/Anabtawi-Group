from odoo import api, fields, models


class ConstructionBudgetPoLine(models.Model):
    _name = "construction.budget.po.line"
    _description = "Construction PO - Bill of Materials Line"
    _order = "po_id, sequence, id"

    po_id = fields.Many2one(
        "construction.budget.po", string="Purchase Order", required=True, ondelete="cascade"
    )
    sequence = fields.Integer(default=10)
    description = fields.Char(string="Material / Work Item", required=True)
    uom = fields.Char(string="UoM")
    quantity = fields.Float(string="Quantity", default=1.0, required=True)
    unit_price = fields.Monetary(string="Unit Price", required=True)
    currency_id = fields.Many2one(related="po_id.currency_id", store=True, readonly=True)
    subtotal = fields.Monetary(string="Subtotal", compute="_compute_subtotal", store=True)

    @api.depends("quantity", "unit_price")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_price
