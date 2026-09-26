from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class ConstructionBudgetInvoice(models.Model):
    _name = "construction.budget.invoice"
    _description = "Construction Vendor Bill / Invoice"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(
        string="Invoice Ref", required=True, copy=False, readonly=True, default=lambda self: _("New")
    )
    po_id = fields.Many2one("construction.budget.po", string="Purchase Order", required=True, tracking=True, ondelete="restrict")
    project_id = fields.Many2one(related="po_id.project_id", store=True, readonly=True)
    vendor_id = fields.Many2one(related="po_id.vendor_id", store=True, readonly=True)
    company_id = fields.Many2one(related="po_id.company_id", store=True, readonly=True)
    currency_id = fields.Many2one(related="po_id.currency_id", store=True, readonly=True)

    date = fields.Date(string="Bill Date", default=fields.Date.context_today, required=True, tracking=True)
    due_date = fields.Date(string="Due Date", default=fields.Date.context_today, required=True)
    vendor_bill_ref = fields.Char(string="Vendor Bill No.", help="Reference / Bill number issued by the vendor")

    amount = fields.Monetary(string="Bill Amount", required=True, tracking=True)
    notes = fields.Text(string="Notes / Payment Terms")

    payment_schedule_id = fields.Many2one(
        "construction.budget.po.payment.schedule",
        string="Payment Milestone",
        domain="[('po_id', '=', po_id)]",
        help="Optional: Link this bill to a specific payment milestone on the PO",
    )

    state = fields.Selection(
        [("draft", "Draft"), ("posted", "Posted"), ("paid", "Paid"), ("cancelled", "Cancelled")],
        default="draft",
        required=True,
        tracking=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("construction.budget.invoice") or _("New")
        return super().create(vals_list)

    def action_post(self):
        for rec in self:
            if rec.state != "draft":
                continue
            if not rec.amount or rec.amount <= 0:
                raise UserError(_("Invoice amount must be greater than zero."))
            rec.state = "posted"
            if rec.payment_schedule_id:
                rec.payment_schedule_id.state = "invoiced"
            rec.message_post(body=_("Vendor bill posted for %s.", rec.amount))
            rec.po_id._compute_invoice_status()

    def action_register_payment(self):
        for rec in self:
            if rec.state != "posted":
                raise UserError(_("Only posted vendor bills can be marked as paid."))
            rec.state = "paid"
            if rec.payment_schedule_id:
                rec.payment_schedule_id.state = "paid"
            rec.message_post(body=_("Payment registered. Bill marked as Paid."))
            rec.po_id._compute_invoice_status()

    def action_cancel(self):
        for rec in self:
            if rec.state == "paid":
                raise UserError(_("Cannot cancel a paid invoice."))
            rec.state = "cancelled"
            if rec.payment_schedule_id and rec.payment_schedule_id.state in ("invoiced", "paid"):
                rec.payment_schedule_id.state = "draft"
            rec.po_id._compute_invoice_status()
