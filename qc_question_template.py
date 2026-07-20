# -*- coding: utf-8 -*-
from odoo import api, fields, models


class QcInspectionFactor(models.Model):
    _name = "qc.inspection.factor"
    _description = "Inspection Factor Result"
    _order = "inspection_id, sequence, id"

    inspection_id = fields.Many2one(
        "qc.inspection", string="Inspection",
        required=True, ondelete="cascade", index=True,
    )
    factor_template_id = fields.Many2one(
        "qc.factor.template", string="Factor Template",
    )
    name = fields.Char(string="Factor", required=True)
    sequence = fields.Integer(default=10)
    max_score = fields.Float(string="Maximum Score", default=10.0)
    company_id = fields.Many2one(
        related="inspection_id.company_id", store=True, index=True,
    )
    branch_id = fields.Many2one(
        related="inspection_id.branch_id", store=True, index=True,
    )
    answer_ids = fields.One2many(
        "qc.inspection.answer", "factor_id", string="Answers",
    )
    score = fields.Float(
        string="Score", compute="_compute_score", store=True,
    )
    percentage = fields.Float(
        string="Percentage", compute="_compute_score", store=True,
    )
    has_critical_failure = fields.Boolean(
        string="Critical Failure", compute="_compute_score", store=True,
    )

    @api.depends(
        "answer_ids.points", "answer_ids.max_points",
        "answer_ids.not_applicable", "answer_ids.critical_failed",
        "max_score",
    )
    def _compute_score(self):
        for factor in self:
            answers = factor.answer_ids.filtered(lambda a: not a.not_applicable)
            earned = sum(answers.mapped("points"))
            possible = sum(answers.mapped("max_points"))
            ratio = (earned / possible) if possible else 0.0
            factor.score = ratio * factor.max_score
            factor.percentage = ratio * 100.0
            factor.has_critical_failure = any(
                factor.answer_ids.mapped("critical_failed"))
