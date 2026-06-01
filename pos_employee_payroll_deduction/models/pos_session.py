from odoo import models


class PosSession(models.Model):
    _inherit = "pos.session"

    def _create_pay_later_receivable_lines(self, data):
        MoveLine = data.get("MoveLine")
        combine_receivables_pay_later = data.get("combine_receivables_pay_later") or {}
        split_receivables_pay_later = data.get("split_receivables_pay_later") or {}
        vals = []

        for payment_method, amounts in combine_receivables_pay_later.items():
            val = self._get_combine_receivable_vals(
                payment_method, amounts["amount"], amounts["amount_converted"]
            )
            if payment_method.is_payroll_due_method:
                val["is_pos_payroll_due"] = True
                val["pos_payment_method_id"] = payment_method.id
            vals.append(val)

        for payment, amounts in split_receivables_pay_later.items():
            payment_method = payment.payment_method_id
            val = self._get_split_receivable_vals(
                payment, amounts["amount"], amounts["amount_converted"]
            )
            if payment_method.is_payroll_due_method:
                val["is_pos_payroll_due"] = True
                val["pos_payment_method_id"] = payment_method.id
            vals.append(val)

        for val in vals:
            # Entries related to a `pay_later` payment method should not be excluded from follow-ups.
            val["no_followup"] = False

        data["pay_later_move_lines"] = MoveLine.create(vals)
        return data
