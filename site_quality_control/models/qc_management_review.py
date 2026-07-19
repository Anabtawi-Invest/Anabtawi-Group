# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class QcManagementReview(models.Model):
    """Management review meeting record (ISO 22000 §9.3).

    Captures the period KPIs (inputs), the discussion and decisions
    (outputs), attendees, and links the follow-up corrective actions."""
    _name = "qc.management.review"
    _description = "Quality Management Review"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(
        string="Reference", required=True, copy=False, readonly=True,
        default=lambda self: _("New"), index=True,
    )
    date = fields.Date(
        string="Review Date", required=True,
        default=fields.Date.context_today, tracking=True,
    )
    period_start = fields.Date(string="Period From", required=True)
    period_end = fields.Date(string="Period To", required=True)
    chair_id = fields.Many2one(
        "res.users", string="Chairperson", required=True, tracking=True,
        default=lambda self: self.env.user,
    )
    attendee_ids = fields.Many2many(
        "res.users", string="Attendees",
    )
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, index=True,
        default=lambda self: self.env.company,
    )
    state = fields.Selection(
        [("draft", "Draft"), ("done", "Completed")],
        string="Status", default="draft", required=True, tracking=True,
    )

    # KPI inputs (computed over the review period)
    avg_score = fields.Float(
        string="Average Inspection Score (%)",
        compute="_compute_kpis", store=False,
    )
    inspection_count = fields.Integer(
        string="Inspections in Period", compute="_compute_kpis", store=False,
    )
    critical_count = fields.Integer(
        string="Critical Failures", compute="_compute_kpis", store=False,
    )
    open_ca_count = fields.Integer(
        string="Open Corrective Actions", compute="_compute_kpis", store=False,
    )
    overdue_ca_count = fields.Integer(
        string="Overdue Corrective Actions", compute="_compute_kpis",
        store=False,
    )

    # Review content
    inputs_summary = fields.Text(
        string="Inputs / Findings",
        help="Audit results, customer complaints, trends, resource needs, "
             "previous review follow-up.",
    )
    decisions = fields.Text(
        string="Decisions / Outputs",
        help="Improvement decisions, resource allocations, policy changes.",
    )
    action_ids = fields.One2many(
        "qc.corrective.action", "management_review_id",
        string="Follow-up Actions",
    )
    note = fields.Text(string="Notes")

    @api.depends("period_start", "period_end", "company_id")
    def _compute_kpis(self):
        Inspection = self.env["qc.inspection"]
        Corrective = self.env["qc.corrective.action"]
        for review in self:
            if not (review.period_start and review.period_end):
                review.avg_score = 0.0
                review.inspection_count = 0
                review.critical_count = 0
                review.open_ca_count = 0
                review.overdue_ca_count = 0
                continue
            inspections = Inspection.search([
                ("inspection_date", ">=", review.period_start),
                ("inspection_date", "<=", review.period_end),
                ("company_id", "=", review.company_id.id),
                ("state", "in", ("reviewed", "approved", "closed")),
            ])
            review.inspection_count = len(inspections)
            review.avg_score = (
                sum(inspections.mapped("percentage")) / len(inspections)
                if inspections else 0.0)
            review.critical_count = len(
                inspections.filtered("has_critical"))
            actions = Corrective.search([
                ("company_id", "=", review.company_id.id),
                ("state", "not in", ("done", "verified", "cancel")),
            ])
            review.open_ca_count = len(actions)
            review.overdue_ca_count = len(actions.filtered("is_overdue"))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                seq = self.env["ir.sequence"].next_by_code(
                    "qc.management.review")
                vals["name"] = seq or _("New")
        return super().create(vals_list)

    def action_done(self):
        for review in self:
            if review.state != "draft":
                raise UserError(_("This review is already completed."))
            if not review.decisions:
                raise UserError(_(
                    "Record the review decisions before completing."))
        self.write({"state": "done"})
        return True

    def action_reopen(self):
        if not self.env.user.has_group(
                "site_quality_control.group_qc_admin"):
            raise UserError(_(
                "Only a Quality Administrator can reopen a completed review."))
        self.write({"state": "draft"})
        return True
