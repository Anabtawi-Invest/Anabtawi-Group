from odoo import fields, models


class HrPayslipInputType(models.Model):
    _inherit = "hr.payslip.input.type"

    overtime_quantity_type = fields.Boolean(
        string="Use Quantity for Overtime",
        help="If enabled, the input quantity represents overtime hours and amount is computed from settings.",
    )
