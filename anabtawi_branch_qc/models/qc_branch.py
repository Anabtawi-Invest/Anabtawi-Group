# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class QcBranch(models.Model):
    _name = "qc.branch"
    _description = "Quality Control Branch"
    _inherit = ["mail.thread"]
    _order = "sequence, name"

    name = fields.Char(string="Branch Name", required=True, tracking=True, translate=True)
    code = fields.Char(string="Code", tracking=True)
    sequence = fields.Integer(default=10)
    region = fields.Char(string="Region", tracking=True)
    manager_id = fields.Many2one(
        "res.users", string="Branch Manager", tracking=True,
    )
    inspector_id = fields.Many2one(
        "res.users", string="Quality Inspector", tracking=True,
    )
    company_id = fields.Many2one(
        "res.company", string="Company", required=True,
        default=lambda self: self.env.company, index=True,
    )
    inspection_frequency = fields.Selection(
        [
            ("weekly", "Weekly"),
            ("monthly", "Monthly"),
            ("quarterly", "Quarterly"),
            ("semiannual", "Semi-annual"),
            ("annual", "Annual"),
        ],
        string="Inspection Frequency", default="monthly", required=True,
    )
    min_passing_score = fields.Float(
        string="Minimum Passing Score", default=60.0,
        help="Total score (out of 100) below which the branch is considered failing.",
    )
    # Optional links to existing operational records; blank by default.
    warehouse_id = fields.Many2one("stock.warehouse", string="Related Warehouse")
    pos_config_id = fields.Many2one("pos.config", string="Related POS")
    active = fields.Boolean(default=True)

    inspection_ids = fields.One2many(
        "qc.inspection", "branch_id", string="Inspections",
    )
    inspection_count = fields.Integer(
        string="Inspections", compute="_compute_inspection_count",
    )
    corrective_action_ids = fields.One2many(
        "qc.corrective.action", "branch_id", string="Corrective Actions",
    )
    open_corrective_count = fields.Integer(
        string="Open Corrective Actions", compute="_compute_corrective_counts",
    )
    overdue_corrective_count = fields.Integer(
        string="Overdue Corrective Actions", compute="_compute_corrective_counts",
    )
    last_score = fields.Float(
        string="Latest Score", compute="_compute_last_score", store=False,
    )
    last_grade_id = fields.Many2one(
        "qc.grade", string="Latest Grade", compute="_compute_last_score", store=False,
    )

    _sql_constraints = [
        ("code_company_uniq",
         "unique(code, company_id)",
         "The branch code must be unique per company."),
    ]

    @api.depends("inspection_ids")
    def _compute_inspection_count(self):
        data = self.env["qc.inspection"]._read_group(
            [("branch_id", "in", self.ids)],
            groupby=["branch_id"], aggregates=["__count"],
        )
        mapped = {branch.id: count for branch, count in data}
        for branch in self:
            branch.inspection_count = mapped.get(branch.id, 0)

    @api.depends("corrective_action_ids.state", "corrective_action_ids.is_overdue")
    def _compute_corrective_counts(self):
        for branch in self:
            actions = branch.corrective_action_ids
            branch.open_corrective_count = len(
                actions.filtered(lambda a: a.state not in ("done", "cancel"))
            )
            branch.overdue_corrective_count = len(
                actions.filtered(lambda a: a.is_overdue)
            )

    def _compute_last_score(self):
        for branch in self:
            last = self.env["qc.inspection"].search(
                [("branch_id", "=", branch.id),
                 ("state", "in", ("reviewed", "approved", "closed"))],
                order="inspection_date desc, id desc", limit=1,
            )
            branch.last_score = last.total_score if last else 0.0
            branch.last_grade_id = last.grade_id if last else False

    @api.constrains("min_passing_score")
    def _check_min_passing_score(self):
        for branch in self:
            if branch.min_passing_score < 0 or branch.min_passing_score > 100:
                raise ValidationError(
                    _("Minimum passing score must be between 0 and 100."))

    def action_view_inspections(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Inspections"),
            "res_model": "qc.inspection",
            "view_mode": "list,form,graph,pivot",
            "domain": [("branch_id", "=", self.id)],
            "context": {"default_branch_id": self.id},
        }

    def action_view_corrective_actions(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Corrective Actions"),
            "res_model": "qc.corrective.action",
            "view_mode": "list,form",
            "domain": [("branch_id", "=", self.id)],
            "context": {"default_branch_id": self.id},
        }
