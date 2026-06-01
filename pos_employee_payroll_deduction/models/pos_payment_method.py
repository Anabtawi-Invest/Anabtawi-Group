from odoo import fields, models


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    is_payroll_due_method = fields.Boolean(
        string="Use for Payroll POS Due",
        help="When enabled, customer-account receivable lines of this method are used in payroll deduction.",
    )
