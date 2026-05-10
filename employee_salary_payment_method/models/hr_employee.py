from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    salary_payment_method = fields.Selection(
        selection=[
            ("one_payment", "One Payment"),
            ("two_payments", "Two Payments"),
        ],
        string="Salary Payment Method",
        default="one_payment",
        required=False,
        tracking=True,
        help="حدد هل سيتم دفع راتب الموظف على دفعة واحدة أو دفعتين.",
    )
