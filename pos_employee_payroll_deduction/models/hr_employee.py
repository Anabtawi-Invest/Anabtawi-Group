from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    pos_debt_partner_id = fields.Many2one(
        "res.partner",
        string="POS Debt Partner",
        help="Customer partner used to map POS receivables to this employee.",
    )
    pos_debt_monthly_limit = fields.Float(
        string="POS Debt Monthly Deduction Limit",
        help="Maximum POS debt deduction per payslip. Keep 0 for no limit.",
    )
