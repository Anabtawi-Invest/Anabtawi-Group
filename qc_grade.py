# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class QcCorrectiveAction(models.Model):
    _name = "qc.corrective.action"
    _description = "Quality Corrective Action"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "due_date, id desc"

    name = fields.Char(
        string="Reference", required=True, copy=False, readonly=True,
        default=lambda self: _("New"), index=True,
    )
    branch_id = fields.Many2one(
        "qc.branch", string="Site", required=True, tracking=True, index=True,
    )
    inspection_id = fields.Many2one(
        "qc.inspection", string="Inspection", tracking=True, index=True,
    )
    factor_id = fields.Many2one(
        "qc.inspection.factor", string="Failed Factor",
        domain="[('inspection_id', '=', inspection_id)]",
    )
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, index=True,
        default=lambda self: self.env.company,
    )
    problem = fields.Text(string="Problem", required=True)
    root_cause = fields.Text(string="Root Cause")
    immediate_action = fields.Text(string="Immediate Action")
    corrective_action = fields.Text(string="Corrective Action")
    responsible_id = fields.Many2one(
        "res.users", string="Responsible", tracking=True,
    )
    due_date = fields.Date(string="Due Date", tracking=True)
    priority = fields.Selection(
        [("0", "Low"), ("1", "Normal"), ("2", "High"), ("3", "Urgent")],
        string="Priority", default="1", tracking=True,
    )
    state = fields.Selection(
        [
            ("new", "New"),
            ("in_progress", "In Progress"),
            ("done", "Done"),
            ("verified", "Verified"),
            ("cancel", "Cancelled"),
        ],
        string="Status", default="new", tracking=True, index=True,
    )
    evidence_before = fields.Binary(string="Evidence Before", attachment=True)
    evidence_after = fields.Binary(string="Evidence After", attachment=True)
    verification_result = fields.Selection(
        [("pass", "Passed"), ("fail", "Failed")], string="Verification Result",
        tracking=True,
    )
    verified_by_id = fields.Many2one("res.users", string="Verified By")
    verification_date = fields.Date(string="Verification Date")
    management_review_id = fields.Many2one(
        "qc.management.review", string="Management Review", index=True,
        help="Set when this action was decided in a management review.",
    )
    sanitation_log_id = fields.Many2one(
        "qc.sanitation.log", string="Sanitation Log", index=True,
        help="Set when this action was raised from a failed sanitation "
             "verification.",
    )
    environmental_monitoring_id = fields.Many2one(
        "qc.environmental.monitoring", string="Environmental Sample",
        index=True,
        help="Set when this action was raised from a failed environmental "
             "monitoring sample.",
    )
    complaint_id = fields.Many2one(
        "qc.complaint", string="Complaint", index=True,
        help="Set when this action was raised from a customer complaint.",
    )
    is_overdue = fields.Boolean(
        string="Overdue", compute="_compute_is_overdue",
        search="_search_is_overdue",
    )

    _sql_constraints = [
        ("name_uniq", "unique(name, company_id)",
         "The corrective action reference must be unique per company."),
    ]

    @api.depends("due_date", "state")
    def _compute_is_overdue(self):
        today = fields.Date.context_today(self)
        for action in self:
            action.is_overdue = bool(
                action.due_date and action.due_date < today
                and action.state not in ("done", "verified", "cancel"))

    def _search_is_overdue(self, operator, value):
        today = fields.Date.context_today(self)
        overdue_domain = [
            "&",
            ("due_date", "<", today),
            ("state", "not in", ("done", "verified", "cancel")),
        ]
        not_overdue_domain = [
            "|", "|",
            ("due_date", "=", False),
            ("due_date", ">=", today),
            ("state", "in", ("done", "verified", "cancel")),
        ]
        want_overdue = (operator == "=" and value) or \
            (operator == "!=" and not value)
        return overdue_domain if want_overdue else not_overdue_domain

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                seq = self.env["ir.sequence"].next_by_code(
                    "qc.corrective.action")
                vals["name"] = seq or _("New")
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Workflow
    # ------------------------------------------------------------------
    def action_start(self):
        self.write({"state": "in_progress"})

    def action_done(self):
        self.write({"state": "done"})

    def action_verify(self):
        for action in self:
            if not action.verification_result:
                raise UserError(_(
                    "Set the verification result before verifying."))
            action.write({
                "state": "verified",
                "verified_by_id": self.env.user.id,
                "verification_date": fields.Date.context_today(self),
            })

    def action_cancel(self):
        self.write({"state": "cancel"})

    def action_reset(self):
        for action in self:
            if action.state == "verified" and not self.env.user.has_group(
                    "site_quality_control.group_qc_quality_manager"):
                raise UserError(_(
                    "Only a Quality Manager can reset a verified "
                    "corrective action back to New."))
        self.write({"state": "new"})

    # ------------------------------------------------------------------
    # Scheduled automation (cron)
    # ------------------------------------------------------------------
    @api.model
    def _cron_escalate_overdue(self):
        """Notify responsibles and branch managers about overdue actions."""
        overdue = self.search([("is_overdue", "=", True)])
        for action in overdue:
            recipients = action.responsible_id | action.branch_id.manager_id
            for user in recipients:
                if not user:
                    continue
                has_activity = action.activity_ids.filtered(
                    lambda a: a.user_id == user)
                if has_activity:
                    continue
                action.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=user.id,
                    summary=_("Overdue corrective action - escalation"),
                    note=_("Corrective action %s is overdue (due %s).") % (
                        action.name, action.due_date),
                )
        return True
