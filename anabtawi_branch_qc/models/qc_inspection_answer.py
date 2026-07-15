# -*- coding: utf-8 -*-
from odoo import api, fields, models


class QcInspectionAnswer(models.Model):
    _name = "qc.inspection.answer"
    _description = "Inspection Answer"
    _order = "factor_id, sequence, id"

    inspection_id = fields.Many2one(
        "qc.inspection", string="Inspection",
        required=True, ondelete="cascade", index=True,
    )
    factor_id = fields.Many2one(
        "qc.inspection.factor", string="Factor",
        required=True, ondelete="cascade", index=True,
    )
    question_template_id = fields.Many2one(
        "qc.question.template", string="Question Template",
    )
    name = fields.Char(string="Question", required=True)
    sequence = fields.Integer(default=10)
    answer_type = fields.Selection(
        [
            ("pass_fail", "Pass / Fail"),
            ("score_5", "Score 0-5"),
            ("score_10", "Score 0-10"),
            ("comment", "Comment only"),
        ],
        string="Answer Type", default="score_10", required=True,
    )
    weight = fields.Float(string="Weight", default=1.0)
    is_critical = fields.Boolean(string="Critical")

    # Captured answer values
    val_pass = fields.Selection(
        [("pass", "Pass"), ("fail", "Fail")], string="Pass/Fail",
    )
    val_score = fields.Float(string="Score")
    comment = fields.Text(string="Comment")
    photo = fields.Binary(string="Photo", attachment=True)
    not_applicable = fields.Boolean(string="Not Applicable")
    corrective_required = fields.Boolean(string="Corrective Action Required")
    answered = fields.Boolean(string="Answered", default=False, copy=False)

    # Derived scoring
    points = fields.Float(compute="_compute_points", store=True)
    max_points = fields.Float(compute="_compute_points", store=True)
    fraction = fields.Float(compute="_compute_points", store=True)
    critical_failed = fields.Boolean(compute="_compute_points", store=True)
    is_answered = fields.Boolean(compute="_compute_is_answered", store=True)

    @api.depends(
        "answer_type", "val_pass", "val_score", "weight",
        "not_applicable", "is_critical", "answered",
    )
    def _compute_points(self):
        for ans in self:
            weight = ans.weight or 1.0
            earned = 0.0
            possible = 0.0
            if ans.not_applicable:
                ans.points = 0.0
                ans.max_points = 0.0
                ans.fraction = 0.0
                ans.critical_failed = False
                continue
            if ans.answer_type == "pass_fail":
                possible = weight
                earned = weight if ans.val_pass == "pass" else 0.0
            elif ans.answer_type == "score_5":
                possible = weight * 5.0
                earned = weight * max(0.0, min(ans.val_score, 5.0))
            elif ans.answer_type == "score_10":
                possible = weight * 10.0
                earned = weight * max(0.0, min(ans.val_score, 10.0))
            else:  # comment only – no score contribution
                possible = 0.0
                earned = 0.0
            ans.points = earned
            ans.max_points = possible
            ans.fraction = (earned / possible) if possible else 0.0
            ans.critical_failed = bool(
                ans.is_critical and ans.answered and possible
                and ans.fraction < 0.5)

    @api.depends("answer_type", "val_pass", "comment", "answered", "not_applicable")
    def _compute_is_answered(self):
        for ans in self:
            if ans.not_applicable:
                ans.is_answered = True
            elif ans.answer_type == "pass_fail":
                ans.is_answered = bool(ans.val_pass)
            elif ans.answer_type == "comment":
                ans.is_answered = bool(ans.comment)
            else:
                ans.is_answered = ans.answered

    @api.onchange("val_pass", "val_score", "comment")
    def _onchange_mark_answered(self):
        for ans in self:
            if ans.val_pass or ans.val_score or ans.comment:
                ans.answered = True

    @api.onchange("not_applicable")
    def _onchange_not_applicable(self):
        for ans in self:
            if ans.not_applicable:
                ans.val_pass = False
                ans.val_score = 0.0
