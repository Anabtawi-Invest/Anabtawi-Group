# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class QcComplaint(models.Model):
    """Customer / internal quality complaint (GMP feedback loop).

    Logged, investigated with a root cause, and closed with a resolution.
    Critical or allergen-related complaints automatically raise a
    corrective action."""
    _name = "qc.complaint"
    _description = "Quality Complaint (GMP)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(
        string="Reference", required=True, copy=False, readonly=True,
        default=lambda self: _("New"), index=True,
    )
    date = fields.Date(
        string="Date Received", required=True, default=fields.Date.context_today,
        tracking=True, index=True,
    )
    branch_id = fields.Many2one(
        "qc.branch", string="Site", required=True, tracking=True, index=True,
    )
    partner_id = fields.Many2one(
        "res.partner", string="Customer",
        help="Optional: the customer who raised the complaint.",
    )
    complaint_type = fields.Selection(
        [
            ("foreign_object", "Foreign Object"),
            ("quality", "Quality / Taste / Appearance"),
            ("allergen", "Allergen Related"),
            ("illness", "Suspected Illness"),
            ("packaging", "Packaging / Labelling"),
            ("service", "Service"),
            ("other", "Other"),
        ],
        string="Complaint Type", default="quality", required=True, tracking=True,
    )
    severity = fields.Selection(
        [("low", "Low"), ("medium", "Medium"), ("high", "High"),
         ("critical", "Critical")],
        string="Severity", default="low", required=True, tracking=True,
    )
    product_description = fields.Char(string="Product")
    lot_id = fields.Many2one("stock.lot", string="Lot / Serial")
    lot_ref = fields.Char(string="Lot Reference")
    description = fields.Text(string="Complaint Details", required=True)
    root_cause = fields.Text(string="Root Cause")
    resolution = fields.Text(string="Resolution / Response to Customer")
    responsible_id = fields.Many2one(
        "res.users", string="Assigned To", tracking=True,
        default=lambda self: self.env.user,
    )
    state = fields.Selection(
        [
            ("new", "New"),
            ("investigating", "Investigating"),
            ("closed", "Closed"),
        ],
        string="Status", default="new", required=True, tracking=True,
        index=True,
    )
    close_date = fields.Date(string="Closed On", readonly=True)
    corrective_action_id = fields.Many2one(
        "qc.corrective.action", string="Corrective Action", readonly=True,
        copy=False,
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
                seq = self.env["ir.sequence"].next_by_code("qc.complaint")
                vals["name"] = seq or _("New")
        complaints = super().create(vals_list)
        for complaint in complaints:
            if complaint.severity == "critical" \
                    or complaint.complaint_type in ("allergen", "illness"):
                complaint._create_corrective_action()
        return complaints

    def action_start_investigation(self):
        for rec in self:
            if rec.state != "new":
                raise UserError(_(
                    "Only new complaints can move to investigation."))
        self.write({"state": "investigating"})
        return True

    def action_close(self):
        for rec in self:
            if rec.state != "investigating":
                raise UserError(_(
                    "Only complaints under investigation can be closed. "
                    "Start the investigation first."))
            if not rec.root_cause or not rec.resolution:
                raise UserError(_(
                    "Record the root cause and resolution before closing "
                    "this complaint."))
            rec.write({
                "state": "closed",
                "close_date": fields.Date.context_today(self),
            })
        return True

    def action_reopen(self):
        if not self.env.user.has_group(
                "site_quality_control.group_qc_quality_manager"):
            raise UserError(_(
                "Only a Quality Manager can reopen a closed complaint."))
        self.write({"state": "investigating", "close_date": False})
        return True

    def _create_corrective_action(self):
        self.ensure_one()
        if self.corrective_action_id:
            return self.corrective_action_id
        action = self.env["qc.corrective.action"].create({
            "branch_id": self.branch_id.id,
            "complaint_id": self.id,
            "problem": _(
                "%(severity)s complaint %(ref)s (%(date)s): %(desc)s") % {
                "severity": dict(self._fields["severity"].selection).get(
                    self.severity, self.severity).upper(),
                "ref": self.name,
                "date": self.date,
                "desc": (self.description or "")[:200],
            },
            "priority": "3" if self.severity == "critical" else "2",
            "responsible_id": self.branch_id.manager_id.id or False,
            "company_id": self.company_id.id,
        })
        self.corrective_action_id = action.id
        return action
