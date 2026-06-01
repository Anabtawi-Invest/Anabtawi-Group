from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    is_pos_payroll_due = fields.Boolean(
        string="POS Payroll Due",
        index=True,
        help="Technical flag used to identify POS customer-account due lines for payroll deductions.",
    )
    pos_payment_method_id = fields.Many2one(
        "pos.payment.method",
        string="POS Payment Method",
        index=True,
        readonly=True,
        copy=False,
    )
