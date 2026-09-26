from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ConstructionBudgetReceipt(models.Model):
    _name = "construction.budget.receipt"
    _description = "Construction Item Receipt / Delivery Note"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(
        string="Receipt Ref", required=True, copy=False, readonly=True, default=lambda self: _("New")
    )
    po_id = fields.Many2one("construction.budget.po", string="Purchase Order", required=True, tracking=True, ondelete="restrict")
    project_id = fields.Many2one(related="po_id.project_id", store=True, readonly=True)
    vendor_id = fields.Many2one(related="po_id.vendor_id", store=True, readonly=True)
    company_id = fields.Many2one(related="po_id.company_id", store=True, readonly=True)
    date = fields.Date(string="Receipt Date", default=fields.Date.context_today, required=True, tracking=True)
    reference = fields.Char(string="Delivery Note / Waybill Ref", help="Vendor delivery note or reference number")
    notes = fields.Text(string="Notes / Inspection Comments")

    state = fields.Selection(
        [("draft", "Draft"), ("done", "Received"), ("cancelled", "Cancelled")],
        default="draft",
        required=True,
        tracking=True,
    )

    line_ids = fields.One2many("construction.budget.receipt.line", "receipt_id", string="Received Items")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.budget.receipt") or _("New")
        return super().create(vals_list)

    def action_validate(self):
        for rec in self:
            if rec.state != "draft":
                continue
            if not rec.line_ids:
                raise UserError(_("Cannot validate a receipt with no received item lines."))
            rec.state = "done"
            rec.message_post(body=_("Receipt validated and items marked as received."))
            rec.po_id._compute_delivery_status()

    def action_cancel(self):
        for rec in self:
            if rec.state == "done":
                raise UserError(_("Cannot cancel a validated receipt."))
            rec.state = "cancelled"


class ConstructionBudgetReceiptLine(models.Model):
    _name = "construction.budget.receipt.line"
    _description = "Construction Item Receipt Line"

    receipt_id = fields.Many2one("construction.budget.receipt", string="Receipt", required=True, ondelete="cascade")
    po_line_id = fields.Many2one("construction.budget.po.line", string="BOM Line", required=True, ondelete="restrict")
    description = fields.Char(related="po_line_id.description", readonly=True)
    uom = fields.Char(related="po_line_id.uom", readonly=True)
    quantity_ordered = fields.Float(related="po_line_id.quantity", string="Ordered Qty", readonly=True)
    quantity_received = fields.Float(string="Received Qty", required=True, default=0.0)
