# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class QcFactorTemplate(models.Model):
    _name = "qc.factor.template"
    _description = "Quality Control Evaluation Factor"
    _order = "template_id, sequence, id"

    name = fields.Char(string="Evaluation Factor", required=True, translate=True)
    sequence = fields.Integer(default=10)
    template_id = fields.Many2one(
        "qc.checklist.template", string="Template",
        required=True, ondelete="cascade", index=True,
    )
    max_score = fields.Float(string="Maximum Score", default=10.0, required=True)
    is_critical_factor = fields.Boolean(
        string="Critical Factor",
        help="If any critical question in this factor fails, the whole "
             "inspection is marked as Failed regardless of the numeric score.",
    )
    question_ids = fields.One2many(
        "qc.question.template", "factor_id", string="Questions", copy=True,
    )
    question_count = fields.Integer(
        string="Questions", compute="_compute_question_count",
    )

    @api.depends("question_ids")
    def _compute_question_count(self):
        for factor in self:
            factor.question_count = len(factor.question_ids)

    @api.constrains("max_score")
    def _check_max_score(self):
        for factor in self:
            if factor.max_score <= 0:
                raise ValidationError(
                    _("Factor '%s': maximum score must be greater than zero.")
                    % factor.name)
