from odoo import api, fields, models


class ConstructionBudgetPoLine(models.Model):
    _name = "construction.budget.po.line"
    _description = "Construction PO - Bill of Materials Line"
    _order = "po_id, sequence, id"

    po_id = fields.Many2one(
        "construction.budget.po", string="Purchase Order", required=True, ondelete="cascade"
    )
    po_project_id = fields.Many2one(related="po_id.project_id", store=True, readonly=True)
    budget_material_id = fields.Many2one(
        "construction.project.budget.material",
        string="Project Budget Material",
        domain="[('project_id', '=', po_project_id), ('state', '=', 'approved')]",
        ondelete="restrict",
    )
    sequence = fields.Integer(default=10)
    description = fields.Char(string="Material / Work Item", required=True)
    uom = fields.Char(string="UoM")
    quantity = fields.Float(string="Quantity", default=1.0, required=True)
    unit_price = fields.Monetary(string="Unit Price", required=True)
    currency_id = fields.Many2one(related="po_id.currency_id", store=True, readonly=True)
    subtotal = fields.Monetary(string="Subtotal", compute="_compute_subtotal", store=True)
    receipt_line_ids = fields.One2many("construction.budget.receipt.line", "po_line_id", string="Receipt Lines")
    qty_received = fields.Float(string="Received Qty", compute="_compute_received_qty", store=True)
    qty_to_receive = fields.Float(string="Remaining Qty", compute="_compute_received_qty", store=True)

    invoice_line_ids = fields.One2many("construction.budget.invoice.line", "po_line_id", string="Invoice Lines")
    qty_invoiced = fields.Float(string="Invoiced Qty", compute="_compute_invoiced_qty", store=True)

    @api.onchange("budget_material_id")
    def _onchange_budget_material_id(self):
        if self.budget_material_id:
            self.description = self.budget_material_id.name
            self.uom = self.budget_material_id.uom
            self.unit_price = self.budget_material_id.unit_cost

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

    @api.depends("invoice_line_ids.quantity", "invoice_line_ids.invoice_id.state")
    def _compute_invoiced_qty(self):
        for line in self:
            posted_inv_lines = line.invoice_line_ids.filtered(
                lambda il: il.invoice_id.state in ("posted", "paid")
            )
            line.qty_invoiced = sum(posted_inv_lines.mapped("quantity"))


