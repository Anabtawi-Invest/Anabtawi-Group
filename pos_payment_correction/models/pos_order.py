from odoo import fields, models, _
from odoo.tools import float_compare


class PosOrder(models.Model):
    _inherit = "pos.order"

    payment_correction_count = fields.Integer(
        string="Payment Corrections",
        compute="_compute_payment_correction_count",
    )

    def _compute_payment_correction_count(self):
        for order in self:
            order.payment_correction_count = len(
                order.payment_ids.filtered("is_payment_correction")
            )

    def _get_order_tax_totals(self):
        res = super()._get_order_tax_totals()
        self.amount_return = self._get_payment_correction_amount_return()
        return res

    def _get_payment_correction_amount_return(self):
        """When fixing payments exist and net paid == total, Returned is 0."""
        self.ensure_one()
        if self.is_refund:
            return self.amount_return
        corrections = self.payment_ids.filtered("is_payment_correction")
        if not corrections:
            return -sum(
                payment.amount for payment in self.payment_ids if payment.amount < 0
            )
        rounding = self.currency_id.rounding
        amount_paid = sum(self.payment_ids.mapped("amount"))
        if float_compare(amount_paid, self.amount_total, precision_rounding=rounding) == 0:
            return 0.0
        return max(0.0, amount_paid - self.amount_total)

    def action_open_payment_correction_wizard(self):
        self.ensure_one()
        return {
            "name": _("Correct POS Payments"),
            "type": "ir.actions.act_window",
            "res_model": "pos.payment.correction.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_order_id": self.id,
            },
        }
