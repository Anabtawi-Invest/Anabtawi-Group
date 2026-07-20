# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class QcGrade(models.Model):
    _name = "qc.grade"
    _description = "Quality Control Grade Band"
    _order = "sequence, min_score desc"

    name = fields.Char(string="Grade", required=True, translate=True)
    letter = fields.Char(string="Letter", required=True)
    classification = fields.Char(string="Classification", translate=True)
    min_score = fields.Float(string="Minimum Score", required=True)
    max_score = fields.Float(string="Maximum Score", required=True, default=100.0)
    sequence = fields.Integer(default=10)
    color = fields.Integer(string="Color")
    active = fields.Boolean(default=True)

    @api.constrains("min_score", "max_score")
    def _check_bounds(self):
        for grade in self:
            if grade.min_score > grade.max_score:
                raise ValidationError(
                    _("Grade '%s': minimum score cannot exceed maximum score.")
                    % grade.name)

    @api.model
    def _grade_for_score(self, score):
        """Return the grade band matching the given total score (0-100)."""
        return self.search(
            [("min_score", "<=", score), ("max_score", ">=", score)],
            order="sequence, min_score desc", limit=1,
        )
