# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class QcChangeControl(models.Model):
    """Change control record (GMP): any planned change to a process,
    recipe, supplier, equipment or facility that could affect food safety
    or quality must be assessed for risk and approved before it is
    implemented, then verified as effective afterwards."""
    _name = "qc.change.control"
    _description = "Change Control (GMP)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(
        string="Reference", required=True, copy=False, readonly=True,
        default=lambda self: _("New"), index=True,
    )
    title = fields.Char(string="Change Title", required=True, tracking=True)
    change_type = fields.Selection(
        [
            ("supplier", "Supplier"),
            ("recipe", "Recipe / Formulation"),
            ("process", "Process"),
            ("equipment", "Equipment"),
            ("facility", "Facility / Layout"),
            ("packaging", "Packaging"),
            ("other", "Other"),
        ],
        string="Change Type", default="process", required=True, tracking=True,
    )
    date = fields.Date(
        string="Request Date", required=True, default=fields.Date.context_today,
        tracking=True,
    )
    branch_ids = fields.Many2many("qc.branch", string="Affected Sites")
    description = fields.Text(string="Description of Change", required=True)
    reason = fields.Text(string="Reason for Change")
    risk_level = fields.Selection(
        [("low", "Low"), ("medium", "Medium"), ("high", "High")],
        string="Risk Level", tracking=True,
    )
    risk_assessment = fields.Text(
        string="Risk Assessment",
        help="Food-safety / quality impact analysis: hazards introduced or "
             "affected, mitigations, whether the HACCP plan or SOPs need "
             "updating.",
    )
    requested_by_id = fields.Many2one(
        "res.users", string="Requested By", tracking=True,
        default=lambda self: self.env.user,
    )
    approved_by_id = fields.Many2one(
        "res.users", string="Approved By", readonly=True, tracking=True,
    )
    approval_date = fields.Date(string="Approval Date", readonly=True)
    rejection_reason = fields.Text(string="Rejection Reason")
    implementation_date = fields.Date(string="Implementation Date", tracking=True)
    implemented_by_id = fields.Many2one("res.users", string="Implemented By")
    verification_date = fields.Date(string="Verification Date")
    verification_result = fields.Selection(
        [("effective", "Effective — No Issues"),
         ("issues", "Issues Found")],
        string="Verification Result", tracking=True,
    )
    verification_notes = fields.Text(string="Verification Notes")
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("implemented", "Implemented"),
            ("verified", "Verified / Closed"),
        ],
        string="Status", default="draft", required=True, tracking=True,
        index=True,
    )
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, index=True,
        default=lambda self: self.env.company,
    )
    note = fields.Text(string="Notes")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                seq = self.env["ir.sequence"].next_by_code("qc.change.control")
                vals["name"] = seq or _("New")
        return super().create(vals_list)

    def _ensure_group(self, message):
        if not self.env.user.has_group(
                "site_quality_control.group_qc_quality_manager"):
            raise UserError(message)

    def action_submit(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("Only draft changes can be submitted."))
            if not rec.description:
                raise UserError(_(
                    "Describe the change before submitting it for review."))
        self.write({"state": "submitted"})
        return True

    def action_approve(self):
        self._ensure_group(_(
            "Only a Quality Manager can approve a change control record."))
        for rec in self:
            if rec.state != "submitted":
                raise UserError(_("Only submitted changes can be approved."))
            if not rec.risk_assessment or not rec.risk_level:
                raise UserError(_(
                    "Complete the risk assessment and risk level before "
                    "approving this change."))
            rec.write({
                "state": "approved",
                "approved_by_id": self.env.user.id,
                "approval_date": fields.Date.context_today(self),
            })
        return True

    def action_reject(self):
        self._ensure_group(_(
            "Only a Quality Manager can reject a change control record."))
        for rec in self:
            if rec.state not in ("submitted", "approved"):
                raise UserError(_(
                    "Only submitted or approved changes can be rejected."))
            if not rec.rejection_reason:
                raise UserError(_(
                    "Enter a rejection reason before rejecting this change."))
        self.write({"state": "rejected"})
        return True

    def action_implement(self):
        for rec in self:
            if rec.state != "approved":
                raise UserError(_(
                    "Only approved changes can be marked as implemented."))
            rec.write({
                "state": "implemented",
                "implementation_date": (
                    rec.implementation_date or fields.Date.context_today(self)),
                "implemented_by_id": self.env.user.id,
            })
        return True

    def action_verify(self):
        self._ensure_group(_(
            "Only a Quality Manager can verify and close a change control "
            "record."))
        for rec in self:
            if rec.state != "implemented":
                raise UserError(_(
                    "Only implemented changes can be verified."))
            if not rec.verification_result:
                raise UserError(_(
                    "Set the verification result before closing this "
                    "change."))
            rec.write({
                "state": "verified",
                "verification_date": fields.Date.context_today(self),
            })
        return True

    def action_reset_to_draft(self):
        self._ensure_group(_(
            "Only a Quality Manager can reset a change control record to "
            "draft."))
        for rec in self:
            if rec.state != "rejected":
                raise UserError(_(
                    "Only rejected changes can be reset to draft."))
        self.write({"state": "draft"})
        return True
