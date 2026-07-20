# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class QcChecklistTemplate(models.Model):
    _name = "qc.checklist.template"
    _description = "Quality Control Checklist Template"
    _order = "name"

    name = fields.Char(string="Template Name", required=True, translate=True)
    checklist_type = fields.Selection(
        [
            ("audit", "Graded Audit"),
            ("daily", "Daily Checklist (no grading)"),
            ("receiving", "Receiving Inspection"),
        ],
        string="Checklist Type", default="audit", required=True,
        help="Graded audits produce a score and a grade. Daily checklists are "
             "simple done/measure lists filled by the site with no scoring.",
    )
    daily_rounds = fields.Selection(
        [("1", "Once a day"), ("2", "Twice a day (morning/evening)"),
         ("3", "Three times a day")],
        string="Rounds per Day", default="1",
        help="How many checklists are generated per day for daily templates.",
    )
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company", string="Company",
        default=lambda self: self.env.company, index=True,
    )
    factor_ids = fields.One2many(
        "qc.factor.template", "template_id", string="Evaluation Factors",
        copy=True,
    )
    total_score = fields.Float(
        string="Total Score", compute="_compute_total_score", store=True,
    )
    factor_count = fields.Integer(
        string="Number of Factors", compute="_compute_total_score", store=True,
    )
    note = fields.Text(string="Notes")

    @api.depends("factor_ids.max_score")
    def _compute_total_score(self):
        for template in self:
            template.total_score = sum(template.factor_ids.mapped("max_score"))
            template.factor_count = len(template.factor_ids)

    def action_view_factors(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Evaluation Factors"),
            "res_model": "qc.factor.template",
            "view_mode": "list,form",
            "domain": [("template_id", "=", self.id)],
            "context": {"default_template_id": self.id},
        }
