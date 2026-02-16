from odoo import models, fields

class HrEmployee(models.Model):
    _inherit = "hr.employee"

    pce_ot_bank_hours = fields.Float(
        string="OT Bank (Hours)",
        default=0.0,
        help="Accumulated overtime hours banked for the employee (hours only; not auto-paid).",
    )
