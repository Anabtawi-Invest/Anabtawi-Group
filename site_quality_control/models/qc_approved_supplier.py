# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class QcApprovedSupplier(models.Model):
    """Approved supplier list (ISO 22000 §7.1.6, BRCGS §3.5).

    Suppliers are approved, conditional or blocked. Receiving inspections
    warn on conditional suppliers and refuse blocked ones."""
    _name = "qc.approved.supplier"
    _description = "Approved Supplier"
    _inherit = ["mail.thread"]
    _order = "partner_id"

    partner_id = fields.Many2one(
        "res.partner", string="Supplier", required=True, tracking=True,
        index=True,
    )
    status = fields.Selection(
        [
            ("approved", "Approved"),
            ("conditional", "Conditional"),
            ("blocked", "Blocked"),
        ],
        string="Status", default="approved", required=True, tracking=True,
    )
    approval_date = fields.Date(
        string="Approval Date", default=fields.Date.context_today,
    )
    expiry_date = fields.Date(
        string="Approval Expires",
        help="Leave empty for approvals without expiry.",
    )
    scope = fields.Char(
        string="Approved Scope", translate=True,
        help="Which goods/services this supplier is approved for.",
    )
    certificates = fields.Text(
        string="Certificates",
        help="e.g. ISO 22000, HACCP, halal certificates with expiry dates.",
    )
    company_id = fields.Many2one(
        "res.company", string="Company",
        default=lambda self: self.env.company, index=True,
    )
    active = fields.Boolean(default=True)
    note = fields.Text(string="Notes")

    _sql_constraints = [
        ("partner_company_uniq", "unique(partner_id, company_id)",
         "This supplier is already on the list for this company."),
    ]

    @api.model
    def _status_for_partner(self, partner, company):
        """Return the supplier's status, or False when not listed."""
        record = self.search([
            ("partner_id", "=", partner.id),
            "|", ("company_id", "=", False),
            ("company_id", "=", company.id),
        ], limit=1)
        return record.status if record else False
