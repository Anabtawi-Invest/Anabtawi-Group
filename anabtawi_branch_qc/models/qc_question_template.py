# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


ANSWER_TYPES = [
    ("pass_fail", "Pass / Fail"),
    ("score_5", "Score 0-5"),
    ("score_10", "Score 0-10"),
    ("comment", "Comment only"),
]


class QcQuestionTemplate(models.Model):
    _name = "qc.question.template"
    _description = "Quality Control Checklist Question"
    _order = "factor_id, sequence, id"

    name = fields.Char(string="Question", required=True, translate=True)
    sequence = fields.Integer(default=10)
    factor_id = fields.Many2one(
        "qc.factor.template", string="Factor",
        required=True, ondelete="cascade", index=True,
    )
    template_id = fields.Many2one(
        related="factor_id.template_id", store=True, string="Template",
    )
    answer_type = fields.Selection(
        ANSWER_TYPES, string="Answer Type", default="score_10", required=True,
    )
    weight = fields.Float(
        string="Weight", default=1.0,
        help="Relative weight of this question within its factor when the "
             "factor score is aggregated.",
    )
    is_critical = fields.Boolean(
        string="Critical",
        help="A failing answer forces the whole inspection to Failed and "
             "makes a corrective action mandatory.",
    )
    allow_na = fields.Boolean(string="Allow Not Applicable", default=True)
    allow_photo = fields.Boolean(string="Allow Photo", default=True)
    help_text = fields.Text(string="Guidance")
