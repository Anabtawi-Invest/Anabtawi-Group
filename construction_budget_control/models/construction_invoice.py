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
    po_id = fields.Many2one(
        "construction.budget.po",
        string="Purchase Order",
        required=True,
        tracking=True,
        ondelete="restrict",
        domain="[('state', '=', 'approved'), ('invoice_status', '!=', 'invoiced')]",
    )
    project_id = fields.Many2one(related="po_id.project_id", store=True, readonly=True)
    vendor_id = fields.Many2one(related="po_id.vendor_id", store=True, readonly=True)
    company_id = fields.Many2one(related="po_id.company_id", store=True, readonly=True)
    currency_id = fields.Many2one(related="po_id.currency_id", store=True, readonly=True)

    date = fields.Date(string="Bill Date", default=fields.Date.context_today, required=True, tracking=True)
    due_date = fields.Date(string="Due Date", default=fields.Date.context_today, required=True)
    vendor_bill_ref = fields.Char(string="Vendor Bill No.", help="Reference / Bill number issued by the vendor")

    line_ids = fields.One2many("construction.budget.invoice.line", "invoice_id", string="Invoice Lines")
    amount = fields.Monetary(string="Bill Amount", compute="_compute_amount", store=True, readonly=False, tracking=True)
    notes = fields.Text(string="Notes / Payment Terms")

    payment_schedule_id = fields.Many2one(
        "construction.budget.po.payment.schedule",
        string="Payment Milestone",
        domain="[('po_id', '=', po_id)]",
        help="Optional: Link this bill to a specific payment milestone on the PO",
    )

    receipt_ids = fields.One2many(related="po_id.receipt_ids", string="Item Receipts")
    receipt_count = fields.Integer(compute="_compute_receipt_count")

    po_received_value = fields.Monetary(
        related="po_id.total_received_value", string="PO Received Inventory Value", readonly=True
    )
    po_already_invoiced_value = fields.Monetary(
        compute="_compute_po_billing_limits", string="Previously Invoiced Amount", store=True
    )
    max_billable_amount = fields.Monetary(
        compute="_compute_po_billing_limits", string="Max Billable Amount", store=True
    )

    state = fields.Selection(
        [("draft", "Draft"), ("posted", "Posted"), ("paid", "Paid"), ("cancelled", "Cancelled")],
        default="draft",
        required=True,
        tracking=True,
    )

    @api.depends("po_id", "po_id.receipt_ids")
    def _compute_receipt_count(self):
        for rec in self:
            rec.receipt_count = len(rec.po_id.receipt_ids) if rec.po_id else 0

    @api.depends("line_ids.subtotal")
    def _compute_amount(self):
        for rec in self:
            if rec.line_ids:
                rec.amount = sum(rec.line_ids.mapped("subtotal"))

    @api.depends("po_id", "po_id.invoice_ids.state", "po_id.invoice_ids.amount", "po_id.total_received_value")
    def _compute_po_billing_limits(self):
        for rec in self:
            if not rec.po_id:
                rec.po_already_invoiced_value = 0.0
                rec.max_billable_amount = 0.0
                continue
            other_invoices = rec.po_id.invoice_ids.filtered(
                lambda i: i.id != rec.id and i.state in ("posted", "paid")
            )
            already_inv = sum(other_invoices.mapped("amount"))
            rec.po_already_invoiced_value = already_inv
            rec.max_billable_amount = max(0.0, rec.po_id.total_received_value - already_inv)

    @api.onchange("po_id")
    def _onchange_po_id(self):
        if not self.po_id:
            self.line_ids = [(5, 0, 0)]
            return
        if self.po_id.state != "approved":
            raise UserError(_("Vendor bills can only be created for approved Purchase Orders."))
        
        new_lines = []
        for po_line in self.po_id.line_ids:
            # calculate qty already invoiced on posted/paid bills
            other_inv_lines = po_line.invoice_line_ids.filtered(
                lambda il: il.invoice_id.id != self.id and il.invoice_id.state in ("posted", "paid")
            )
            prev_inv_qty = sum(other_inv_lines.mapped("quantity"))
            unbilled_qty = max(0.0, po_line.qty_received - prev_inv_qty)
            if unbilled_qty > 0:
                new_lines.append((0, 0, {
                    "po_line_id": po_line.id,
                    "quantity": unbilled_qty,
                    "unit_price": po_line.unit_price,
                }))
        self.line_ids = [(5, 0, 0)] + new_lines

    @api.constrains("amount", "line_ids", "po_id", "state")
    def _check_received_inventory_limit(self):
        for rec in self:
            if rec.state in ("posted", "paid"):
                if not rec.po_id:
                    raise ValidationError(_("Vendor bill must be linked to a Purchase Order."))
                if rec.po_id.state != "approved":
                    raise ValidationError(_("Vendor bill can only be posted for an approved Purchase Order."))
                
                # Check 1: total bill amount cannot exceed received inventory value
                other_invoices = rec.po_id.invoice_ids.filtered(
                    lambda i: i.id != rec.id and i.state in ("posted", "paid")
                )
                prev_billed = sum(other_invoices.mapped("amount"))
                received_value = rec.po_id.total_received_value
                max_allowed = max(0.0, received_value - prev_billed)

                if rec.amount > max_allowed + 1e-4:
                    raise ValidationError(_(
                        "Cannot pay/bill more than the monetary value of inventory received for PO '%(po)s'!\n"
                        "Total received inventory value: %(rec_val)s\n"
                        "Previously billed/paid: %(prev)s\n"
                        "Max billable/payable now: %(max_bill)s\n"
                        "Attempted bill amount: %(amt)s"
                    ) % {
                        "po": rec.po_id.name,
                        "rec_val": received_value,
                        "prev": prev_billed,
                        "max_bill": max_allowed,
                        "amt": rec.amount,
                    })

                # Check 2: validate individual line items
                for line in rec.line_ids:
                    if line.quantity > line.qty_received - line.qty_previously_invoiced + 1e-4:
                        raise ValidationError(_(
                            "Cannot bill line '%(item)s' for quantity %(qty)s. Maximum received quantity available to bill is %(avail)s."
                        ) % {
                            "item": line.description,
                            "qty": line.quantity,
                            "avail": max(0.0, line.qty_received - line.qty_previously_invoiced),
                        })

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
            if not rec.po_id or rec.po_id.state != "approved":
                raise UserError(_("Vendor bill can only be posted for an approved Purchase Order."))
            if not rec.amount or rec.amount <= 0:
                raise UserError(_("Invoice amount must be greater than zero."))
            
            # Verify inventory payment restriction
            rec._check_received_inventory_limit()

            rec.state = "posted"
            if rec.payment_schedule_id:
                rec.payment_schedule_id.state = "invoiced"
            rec.message_post(body=_("Vendor bill posted for %s.", rec.amount))
            rec.po_id._compute_invoice_status()

    def action_register_payment(self):
        for rec in self:
            if rec.state != "posted":
                raise UserError(_("Only posted vendor bills can be marked as paid."))
            
            # Verify inventory payment restriction before releasing payment
            rec._check_received_inventory_limit()

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


class ConstructionBudgetInvoiceLine(models.Model):
    _name = "construction.budget.invoice.line"
    _description = "Construction Vendor Bill Line"

    invoice_id = fields.Many2one("construction.budget.invoice", string="Vendor Bill", required=True, ondelete="cascade")
    po_line_id = fields.Many2one("construction.budget.po.line", string="PO Line", required=True, ondelete="restrict")
    budget_material_id = fields.Many2one(related="po_line_id.budget_material_id", store=True, readonly=True)
    description = fields.Char(related="po_line_id.description", readonly=True)
    uom = fields.Char(related="po_line_id.uom", readonly=True)

    qty_ordered = fields.Float(related="po_line_id.quantity", string="Ordered Qty", readonly=True)
    qty_received = fields.Float(related="po_line_id.qty_received", string="Received Qty", readonly=True)
    qty_previously_invoiced = fields.Float(string="Prev. Invoiced Qty", compute="_compute_prev_invoiced_qty")

    quantity = fields.Float(string="Quantity to Bill", required=True, default=1.0)
    unit_price = fields.Monetary(string="Unit Price", required=True)
    currency_id = fields.Many2one(related="invoice_id.currency_id", store=True, readonly=True)
    subtotal = fields.Monetary(string="Subtotal", compute="_compute_subtotal", store=True)

    @api.depends("po_line_id", "invoice_id.state", "invoice_id.po_id")
    def _compute_prev_invoiced_qty(self):
        for line in self:
            if not line.po_line_id:
                line.qty_previously_invoiced = 0.0
                continue
            other_lines = line.po_line_id.invoice_line_ids.filtered(
                lambda il: il.id != line.id and il.invoice_id.state in ("posted", "paid")
            )
            line.qty_previously_invoiced = sum(other_lines.mapped("quantity"))

    @api.depends("quantity", "unit_price")
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.unit_price
