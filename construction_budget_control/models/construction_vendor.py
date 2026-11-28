from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class ConstructionVendor(models.Model):
    _name = "construction.vendor"
    _description = "Construction Vendor / Subcontractor"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(string="Vendor / Subcontractor Name", required=True, tracking=True)
    code = fields.Char(string="Vendor Code", tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", string="Company", default=lambda self: self.env.company, required=True)
    currency_id = fields.Many2one(related="company_id.currency_id", string="Currency", readonly=True)

    phone = fields.Char(string="Phone")
    mobile = fields.Char(string="Mobile")
    email = fields.Char(string="Email")
    website = fields.Char(string="Website")
    vat = fields.Char(string="Tax ID / Commercial Reg")

    street = fields.Char(string="Street")
    street2 = fields.Char(string="Street 2")
    city = fields.Char(string="City")
    state_id = fields.Many2one("res.country.state", string="State")
    zip = fields.Char(string="ZIP")
    country_id = fields.Many2one("res.country", string="Country")

    notes = fields.Text(string="Notes / Payment Instructions")

    po_ids = fields.One2many("construction.budget.po", "vendor_id", string="Purchase Orders")
    po_count = fields.Integer(compute="_compute_counts", string="PO Count")

    receipt_ids = fields.One2many("construction.budget.receipt", "vendor_id", string="Item Receipts")
    receipt_count = fields.Integer(compute="_compute_counts", string="Receipt Count")

    construction_invoice_ids = fields.One2many("construction.budget.invoice", "vendor_id", string="Vendor Bills")
    construction_invoice_count = fields.Integer(compute="_compute_counts", string="Vendor Bill Count")

    @api.depends("po_ids", "receipt_ids", "construction_invoice_ids")
    def _compute_counts(self):
        for vendor in self:
            vendor.po_count = len(vendor.po_ids)
            vendor.receipt_count = len(vendor.receipt_ids)
            vendor.construction_invoice_count = len(vendor.construction_invoice_ids)

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
