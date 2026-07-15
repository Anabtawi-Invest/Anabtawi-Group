# -*- coding: utf-8 -*-
from odoo import api, fields, models, tools


class QcBranchRanking(models.Model):
    """Read-only SQL view: one row per branch with its latest inspection,
    previous score, deltas and open/overdue corrective action counts."""
    _name = "qc.branch.ranking"
    _description = "Branch Quality Ranking"
    _auto = False
    _order = "current_score desc"

    branch_id = fields.Many2one("qc.branch", string="Branch", readonly=True)
    template_id = fields.Many2one("qc.checklist.template", string="Checklist Template", readonly=True)
    company_id = fields.Many2one("res.company", string="Company", readonly=True)
    inspection_id = fields.Many2one(
        "qc.inspection", string="Latest Inspection", readonly=True)
    rank = fields.Integer(string="Rank", readonly=True)
    current_score = fields.Float(string="Current Score", readonly=True)
    grade_id = fields.Many2one("qc.grade", string="Grade", readonly=True)
    previous_score = fields.Float(string="Previous Score", readonly=True)
    score_diff = fields.Float(string="Score Difference", readonly=True)
    has_critical = fields.Boolean(string="Critical Failure", readonly=True)
    critical_count = fields.Integer(string="Critical Failures", readonly=True)
    open_corrective = fields.Integer(
        string="Open Corrective Actions", readonly=True)
    overdue_corrective = fields.Integer(
        string="Overdue Corrective Actions", readonly=True)
    priority_band = fields.Selection(
        [
            ("urgent", "Urgent (< 60)"),
            ("high", "High (60-69.99)"),
            ("monitor", "Improvement Monitoring (70-79.99)"),
            ("good", "Good (80-89.99)"),
            ("excellence", "Excellence (90+)"),
        ],
        string="Priority Band", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                WITH ranked AS (
                    SELECT
                        i.id AS inspection_id,
                        i.branch_id,
                        i.template_id,
                        i.company_id,
                        i.percentage,
                        i.grade_id,
                        i.has_critical,
                        i.inspection_date,
                        row_number() OVER (
                            PARTITION BY i.branch_id, i.template_id
                            ORDER BY i.inspection_date DESC, i.id DESC
                        ) AS rn
                    FROM qc_inspection i
                    WHERE i.state IN ('reviewed', 'approved', 'closed')
                ),
                crit AS (
                    SELECT f.inspection_id, COUNT(*) AS critical_count
                    FROM qc_inspection_factor f
                    WHERE f.has_critical_failure = TRUE
                    GROUP BY f.inspection_id
                ),
                corr AS (
                    SELECT
                        c.branch_id,
                        COUNT(*) FILTER (
                            WHERE c.state NOT IN ('done', 'verified', 'cancel')
                        ) AS open_corrective,
                        COUNT(*) FILTER (
                            WHERE c.state NOT IN ('done', 'verified', 'cancel')
                              AND c.due_date IS NOT NULL
                              AND c.due_date < CURRENT_DATE
                        ) AS overdue_corrective
                    FROM qc_corrective_action c
                    GROUP BY c.branch_id
                )
                SELECT
                    row_number() OVER (ORDER BY base.current_score DESC) AS id,
                    base.branch_id,
                    base.template_id,
                    base.company_id,
                    base.inspection_id,
                    RANK() OVER (ORDER BY base.current_score DESC) AS rank,
                    base.current_score,
                    base.grade_id,
                    base.previous_score,
                    base.current_score - base.previous_score AS score_diff,
                    base.has_critical,
                    base.critical_count,
                    base.open_corrective,
                    base.overdue_corrective,
                    CASE
                        WHEN base.current_score < 60 THEN 'urgent'
                        WHEN base.current_score < 70 THEN 'high'
                        WHEN base.current_score < 80 THEN 'monitor'
                        WHEN base.current_score < 90 THEN 'good'
                        ELSE 'excellence'
                    END AS priority_band
                FROM (
                    SELECT
                        cur.branch_id,
                        cur.template_id,
                        cur.company_id,
                        cur.inspection_id,
                        cur.percentage AS current_score,
                        cur.grade_id,
                        cur.has_critical,
                        COALESCE(prev.percentage, 0.0) AS previous_score,
                        COALESCE(crit.critical_count, 0) AS critical_count,
                        COALESCE(corr.open_corrective, 0) AS open_corrective,
                        COALESCE(corr.overdue_corrective, 0) AS overdue_corrective
                    FROM ranked cur
                    LEFT JOIN ranked prev
                        ON prev.branch_id = cur.branch_id AND prev.template_id = cur.template_id AND prev.rn = 2
                    LEFT JOIN crit ON crit.inspection_id = cur.inspection_id
                    LEFT JOIN corr ON corr.branch_id = cur.branch_id
                    WHERE cur.rn = 1
                ) base
            )
        """ % (self._table,))
