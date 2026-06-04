# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, models
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    def action_post(self):
        for payment in self:
            if (
                payment.partner_type in ("customer", "supplier")
                and payment.currency_id
                and payment.currency_id.is_zero(payment.amount)
            ):
                raise UserError(
                    _(
                        "You cannot confirm a customer/vendor payment with a zero amount. "
                        "Please set an amount greater than zero."
                    )
                )
        return super().action_post()
