# -*- coding: utf-8 -*-
from odoo import api, fields, models


class QcTrainingRecord(models.Model):
    """Food-safety training / competency record (ISO 22000 §7.2).

    One record per employee per training topic, with validity period and
    certificate attachment. Expired records are flagged for renewal."""
    _name = "qc.training.record"
    _description = "Quality Training Record"
    _inherit = ["mail.thread"]
    _order = "date desc, id desc"

    name = fields.Char(string="Training Topic", required=True, tracking=True,
                       translate=True,
                       help="e.g. Food hygiene basics, HACCP awareness, "
                            "Allergen handling, Cleaning & sanitation")
    employee_id = fields.Many2one(
        "hr.employee", string="Employee", required=True, tracking=True,
        index=True,
    )
    branch_id = fields.Many2one(
        "qc.branch", string="Site", tracking=True, index=True,
    )
    date = fields.Date(
        string="Training Date", required=True,
        default=fields.Date.context_today, tracking=True,
    )
    trainer = fields.Char(
        string="Trainer / Provider",
        help="Internal trainer or external training provider.",
    )
    valid_until = fields.Date(
        string="Valid Until", tracking=True,
        help="Leave empty for trainings that do not expire.",
    )
    result = fields.Selection(
        [("pass", "Passed"), ("fail", "Failed")],
        string="Result", default="pass", required=True, tracking=True,
    )
    certificate = fields.Binary(string="Certificate", attachment=True)
    certificate_name = fields.Char(string="Certificate Filename")
    company_id = fields.Many2one(
        "res.company", string="Company",
        default=lambda self: self.env.company, index=True,
    )
    is_expired = fields.Boolean(
        string="Expired", compute="_compute_is_expired",
        search="_search_is_expired",
    )
    note = fields.Text(string="Notes")

    def _compute_is_expired(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.is_expired = bool(rec.valid_until and rec.valid_until < today)

    def _search_is_expired(self, operator, value):
        today = fields.Date.context_today(self)
        expired = [("valid_until", "!=", False), ("valid_until", "<", today)]
        want = (operator == "=" and value) or (operator == "!=" and not value)
        if want:
            return expired
        return ["|", ("valid_until", "=", False),
                ("valid_until", ">=", today)]
