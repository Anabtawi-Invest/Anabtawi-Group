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
    receipt_line_ids = fields.One2many("construction.budget.receipt.line", "po_line_id", string="Receipt Lines")
    qty_received = fields.Float(string="Received Qty", compute="_compute_received_qty", store=True)
    qty_to_receive = fields.Float(string="Remaining Qty", compute="_compute_received_qty", store=True)

    @api.depends("quantity", "unit_price")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_price

    @api.depends("quantity", "receipt_line_ids.quantity_received", "receipt_line_ids.receipt_id.state")
    def _compute_received_qty(self):
        for line in self:
            done_receipts = line.receipt_line_ids.filtered(lambda r: r.receipt_id.state == "done")
            received = sum(done_receipts.mapped("quantity_received"))
            line.qty_received = received
            line.qty_to_receive = max(0.0, line.quantity - received)

