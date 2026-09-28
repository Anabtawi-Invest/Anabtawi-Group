from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_construction_vendor = fields.Boolean(
        string="Is Construction Vendor",
        default=False,
        help="Flag indicating this vendor/partner is managed under Construction Budget Control.",
    )
    po_ids = fields.One2many("construction.budget.po", "vendor_id", string="Construction POs")
    po_count = fields.Integer(compute="_compute_construction_counts", string="PO Count")

    invoice_ids = fields.One2many("construction.budget.invoice", "vendor_id", string="Construction Invoices")
    invoice_count = fields.Integer(compute="_compute_construction_counts", string="Invoice Count")

    receipt_ids = fields.One2many("construction.budget.receipt", "vendor_id", string="Construction Receipts")
    receipt_count = fields.Integer(compute="_compute_construction_counts", string="Receipt Count")

    @api.depends("po_ids", "invoice_ids", "receipt_ids")
    def _compute_construction_counts(self):
        for partner in self:
            partner.po_count = len(partner.po_ids)
            partner.invoice_count = len(partner.invoice_ids)
            partner.receipt_count = len(partner.receipt_ids)

    def action_view_construction_pos(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Purchase Orders"),
            "res_model": "construction.budget.po",
            "view_mode": "list,form",
            "domain": [("vendor_id", "=", self.id)],
            "context": {"default_vendor_id": self.id},
        }

    def action_view_construction_invoices(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Vendor Bills"),
            "res_model": "construction.budget.invoice",
            "view_mode": "list,form",
            "domain": [("vendor_id", "=", self.id)],
            "context": {"default_vendor_id": self.id},
        }

    def action_view_construction_receipts(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Item Receipts"),
            "res_model": "construction.budget.receipt",
            "view_mode": "list,form",
            "domain": [("vendor_id", "=", self.id)],
            "context": {"default_vendor_id": self.id},
        }
