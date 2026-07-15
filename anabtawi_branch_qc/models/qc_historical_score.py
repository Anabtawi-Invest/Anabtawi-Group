# -*- coding: utf-8 -*-
from odoo import api, fields, models


class QcHistoricalScore(models.Model):
    """Imported overall branch results from before the module went live.

    Kept separate from qc.inspection because live inspection scores are
    computed from the checklist; historical records only carry an overall
    total, so they are stored as their own read-friendly rows for ranking
    and trend analysis.
    """
    _name = "qc.historical.score"
    _description = "Historical Branch Score"
    _order = "period_date desc, branch_id"

    branch_id = fields.Many2one(
        "qc.branch", string="Branch", required=True, index=True,
    )
    name = fields.Char(
        string="Period Label", required=True,
        help="Free-text period, e.g. '2024', 'Q4 2024' or 'Jan 2025'.",
    )
    period_date = fields.Date(
        string="Period Date", required=True, index=True,
        help="Representative date used for trend charts (e.g. month end).",
    )
    total_score = fields.Float(
        string="Score (out of 100)", required=True,
    )
    grade_id = fields.Many2one(
        "qc.grade", string="Grade", compute="_compute_grade", store=True,
    )
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, index=True,
        default=lambda self: self.env.company,
    )
    source = fields.Char(string="Source", help="Origin of the imported figure.")
    note = fields.Text(string="Notes")

    _sql_constraints = [
        ("branch_period_uniq",
         "unique(branch_id, name, company_id)",
         "A historical score already exists for this branch and period."),
    ]

    @api.depends("total_score")
    def _compute_grade(self):
        for rec in self:
            grade = self.env["qc.grade"]._grade_for_score(rec.total_score)
            rec.grade_id = grade.id if grade else False
