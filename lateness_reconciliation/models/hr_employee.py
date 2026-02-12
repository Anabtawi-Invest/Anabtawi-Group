from odoo import models, fields

class HrEmployee(models.Model):
    _inherit = "hr.employee"

    ot_hours_bank = fields.Float(
        string="OT Bank (Hours)",
        help="Overtime hours available to offset lateness for reconciliation.",
        default=0.0,
    )
