from odoo import models, fields

class HrEmployee(models.Model):
    _inherit = "hr.employee"

    # Banked overtime HOURS (not auto-paid). Paid manually via Salary Inputs / payslip rules.
    pce_ot_bank_hours = fields.Float(
        string="OT Bank (Hours)",
        default=0.0,
        help="Accumulated banked overtime hours for the employee (hours only; not auto-paid).",
    )
