# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class QcDocument(models.Model):
    """Controlled SOP / quality document register (ISO 22000 §7.5).

    Versioned documents with an approval flow and periodic review dates.
    Checklist factors can reference the SOP that governs them."""
    _name = "qc.document"
    _description = "Controlled Quality Document (SOP)"
    _inherit = ["mail.thread"]
    _order = "code, version desc"

    name = fields.Char(string="Document Title", required=True, tracking=True,
                       translate=True)
    code = fields.Char(string="Document Code", required=True, tracking=True,
                       help="e.g. SOP-CLN-001")
    version = fields.Integer(string="Version", default=1, required=True,
                             tracking=True)
    document_type = fields.Selection(
        [
            ("sop", "SOP / Procedure"),
            ("policy", "Policy"),
            ("form", "Form / Record Template"),
            ("haccp", "HACCP Plan"),
            ("other", "Other"),
        ],
        string="Type", default="sop", required=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("approved", "Approved"),
            ("obsolete", "Obsolete"),
        ],
        string="Status", default="draft", required=True, tracking=True,
    )
    file = fields.Binary(string="File", attachment=True)
    file_name = fields.Char(string="File Name")
    approved_by_id = fields.Many2one(
        "res.users", string="Approved By", readonly=True, tracking=True,
    )
    approval_date = fields.Date(string="Approval Date", readonly=True)
    review_due_date = fields.Date(
        string="Next Review Due", tracking=True,
        help="Date by which this document must be reviewed again.",
    )
    is_review_due = fields.Boolean(
        string="Review Due", compute="_compute_is_review_due",
        search="_search_is_review_due",
    )
    company_id = fields.Many2one(
        "res.company", string="Company",
        default=lambda self: self.env.company, index=True,
    )
    active = fields.Boolean(default=True)
    note = fields.Text(string="Notes")

    _sql_constraints = [
        ("code_version_company_uniq", "unique(code, version, company_id)",
         "This document code + version already exists."),
    ]

    def _compute_is_review_due(self):
        today = fields.Date.context_today(self)
        for doc in self:
            doc.is_review_due = bool(
                doc.state == "approved" and doc.review_due_date
                and doc.review_due_date <= today)

    def _search_is_review_due(self, operator, value):
        today = fields.Date.context_today(self)
        due = [
            ("state", "=", "approved"),
            ("review_due_date", "!=", False),
            ("review_due_date", "<=", today),
        ]
        want_due = (operator == "=" and value) or \
            (operator == "!=" and not value)
        if want_due:
            return due
        return ["|", "|",
                ("state", "!=", "approved"),
                ("review_due_date", "=", False),
                ("review_due_date", ">", today)]

    def action_approve(self):
        if not self.env.user.has_group(
                "site_quality_control.group_qc_quality_manager"):
            raise UserError(_(
                "Only a Quality Manager can approve documents."))
        for doc in self:
            if doc.state != "draft":
                raise UserError(_("Only draft documents can be approved."))
            doc.write({
                "state": "approved",
                "approved_by_id": self.env.user.id,
                "approval_date": fields.Date.context_today(self),
            })
        return True

    def action_obsolete(self):
        if not self.env.user.has_group(
                "site_quality_control.group_qc_quality_manager"):
            raise UserError(_(
                "Only a Quality Manager can obsolete documents."))
        self.write({"state": "obsolete"})
        return True

    def action_new_version(self):
        """Create the next draft version of this document."""
        self.ensure_one()
        new = self.copy({
            "version": self.version + 1,
            "state": "draft",
            "approved_by_id": False,
            "approval_date": False,
        })
        return {
            "type": "ir.actions.act_window",
            "res_model": "qc.document",
            "res_id": new.id,
            "view_mode": "form",
        }
