from odoo import models, fields

class PCESmartReview(models.Model):
    _name = "pce.smart.review"
    _description = "PCE Smart Review"

    employee_id = fields.Many2one("hr.employee")
    payslip_id = fields.Many2one("hr.payslip")

    lateness_hours = fields.Float()
    ot_total_hours = fields.Float()
    annual_leave_hours = fields.Float()
    remaining_hours = fields.Float()
