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

    invoice_ids = fields.One2many(related="po_id.invoice_ids", string="Vendor Invoices")
    invoice_count = fields.Integer(compute="_compute_invoice_count")

    @api.depends("po_id.invoice_ids")
    def _compute_invoice_count(self):
        for rec in self:
            rec.invoice_count = len(rec.po_id.invoice_ids) if rec.po_id else 0

    def action_view_po(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Purchase Order"),
            "res_model": "construction.budget.po",
            "res_id": self.po_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_invoices(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Vendor Bills"),
            "res_model": "construction.budget.invoice",
            "view_mode": "list,form",
            "domain": [("po_id", "=", self.po_id.id)] if self.po_id else [],
            "context": {"default_po_id": self.po_id.id} if self.po_id else {},
        }

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
            
            # Validate received quantity limits before validating receipt
            for line in rec.line_ids:
                line._check_received_qty_limit()

            rec.state = "done"
            rec.message_post(body=_("Receipt validated and items marked as received."))
            rec.po_id._compute_delivery_status()

    def _check_three_approvers_deletion_auth(self):
        user = self.env.user
        if user.has_group("base.group_system"):
            return
        manager_group = self.env.ref("construction_budget_control.group_construction_manager", raise_if_not_found=False)
        accounting_group = self.env.ref("construction_budget_control.group_construction_accounting_approver", raise_if_not_found=False)
        gm_group = self.env.ref("construction_budget_control.group_construction_gm_approver", raise_if_not_found=False)
        chairman_group = self.env.ref("construction_budget_control.group_construction_chairman_approver", raise_if_not_found=False)

        is_manager = manager_group and user in manager_group.user_ids
        has_all_three = (
            accounting_group and user in accounting_group.user_ids and
            gm_group and user in gm_group.user_ids and
            chairman_group and user in chairman_group.user_ids
        )

        if not (is_manager or has_all_three):
            raise AccessError(_(
                "Deletion Restricted: You cannot delete records without the approval authorization of all three approver roles "
                "(Accounting Manager, CEO, and Chairman)."
            ))

    def unlink(self):
        self._check_three_approvers_deletion_auth()
        return super().unlink()

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

    @api.constrains("quantity_received", "po_line_id")
    def _check_received_qty_limit(self):
        for line in self:
            if line.quantity_received < 0:
                raise ValidationError(_("Received quantity cannot be negative."))
            if not line.po_line_id:
                continue

            # Calculate total received quantity from all other validated receipts
            other_receipt_lines = line.po_line_id.receipt_line_ids.filtered(
                lambda r: r.id != line.id and r.receipt_id.state == "done"
            )
            already_received = sum(other_receipt_lines.mapped("quantity_received"))
            max_allowed = max(0.0, line.po_line_id.quantity - already_received)

            if line.quantity_received > max_allowed + 1e-4:
                raise ValidationError(_(
                    "Cannot receive quantity %(received)s for item '%(item)s'!\n"
                    "Ordered Quantity: %(ordered)s\n"
                    "Previously Received: %(prev)s\n"
                    "Maximum Allowed to Receive Now: %(max_allowed)s"
                ) % {
                    "received": line.quantity_received,
                    "item": line.description or line.po_line_id.description,
                    "ordered": line.po_line_id.quantity,
                    "prev": already_received,
                    "max_allowed": max_allowed,
                })
