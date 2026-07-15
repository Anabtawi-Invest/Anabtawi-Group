# -*- coding: utf-8 -*-
from odoo import fields, models


class QcHistoricalFactorAverage(models.Model):
    """Imported overall factor averages (the ten factor averages from the
    historical summary). Per-branch/per-factor detail is not available in the
    source data, so this holds one average per factor per period."""
    _name = "qc.historical.factor.average"
    _description = "Historical Factor Average"
    _order = "period_date desc, name"

    name = fields.Char(string="Evaluation Factor", required=True)
    factor_template_id = fields.Many2one(
        "qc.factor.template", string="Linked Factor",
        help="Optional link to a checklist factor for matching by name.",
    )
    period_date = fields.Date(
        string="Period Date", required=True, index=True,
    )
    period_label = fields.Char(string="Period Label", required=True)
    average_score = fields.Float(
        string="Average Score (out of 10)", required=True,
    )
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, index=True,
        default=lambda self: self.env.company,
    )
    source = fields.Char(string="Source")

    _sql_constraints = [
        ("factor_period_uniq",
         "unique(name, period_label, company_id)",
         "A historical average already exists for this factor and period."),
    ]
