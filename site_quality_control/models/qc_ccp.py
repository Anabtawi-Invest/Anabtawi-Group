# -*- coding: utf-8 -*-
from odoo import api, fields, models


class QcCcp(models.Model):
    """Critical Control Point register (HACCP).

    Documents the hazard behind each critical checklist question: process
    step, hazard type, critical limit and monitoring frequency. Checklist
    questions reference a CCP so every recorded failure is traceable to the
    hazard analysis."""
    _name = "qc.ccp"
    _description = "Critical Control Point (HACCP)"
    _order = "sequence, code"

    code = fields.Char(string="CCP Code", required=True)
    name = fields.Char(string="Name", required=True, translate=True)
    sequence = fields.Integer(default=10)
    process_step = fields.Char(
        string="Process Step", translate=True,
        help="Where in the process this control point applies "
             "(e.g. cold storage, receiving, display).",
    )
    hazard_type = fields.Selection(
        [
            ("biological", "Biological"),
            ("chemical", "Chemical"),
            ("physical", "Physical"),
            ("allergen", "Allergen"),
        ],
        string="Hazard Type", required=True, default="biological",
    )
    hazard_description = fields.Text(
        string="Hazard Description", translate=True,
    )
    critical_limit = fields.Char(
        string="Critical Limit", translate=True,
        help="The measurable limit separating acceptable from unacceptable "
             "(e.g. 0-5 °C).",
    )
    monitoring_frequency = fields.Selection(
        [
            ("continuous", "Continuous"),
            ("per_batch", "Per Batch / Delivery"),
            ("per_round", "Every Round"),
            ("daily", "Daily"),
            ("weekly", "Weekly"),
            ("monthly", "Monthly"),
        ],
        string="Monitoring Frequency", default="daily", required=True,
    )
    corrective_guidance = fields.Text(
        string="Corrective Guidance", translate=True,
        help="What to do immediately when the critical limit is breached.",
    )
    company_id = fields.Many2one(
        "res.company", string="Company",
        default=lambda self: self.env.company, index=True,
    )
    active = fields.Boolean(default=True)
    question_ids = fields.One2many(
        "qc.question.template", "ccp_id", string="Linked Questions",
    )

    _sql_constraints = [
        ("code_company_uniq", "unique(code, company_id)",
         "The CCP code must be unique per company."),
    ]

    @api.depends("code", "name")
    def _compute_display_name(self):
        for ccp in self:
            ccp.display_name = (
                "%s - %s" % (ccp.code, ccp.name) if ccp.code else ccp.name)
