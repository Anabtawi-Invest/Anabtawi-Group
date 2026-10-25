from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PosPayment(models.Model):
    _inherit = "pos.payment"

    is_payment_correction = fields.Boolean(
        string="Fixing Payment",
        default=False,
        help="Mark this payment as a correction that offsets one or more wrong payments.",
        index=True,
    )
    corrected_payment_ids = fields.Many2many(
        comodel_name="pos.payment",
        relation="pos_payment_correction_rel",
        column1="correction_payment_id",
        column2="wrong_payment_id",
        string="Wrong Payments",
        help="Original wrong payment lines this correction offsets.",
    )
    correction_of_ids = fields.Many2many(
        comodel_name="pos.payment",
        relation="pos_payment_correction_rel",
        column1="wrong_payment_id",
        column2="correction_payment_id",
        string="Correction Payments",
        help="Correction payments that offset this payment.",
    )
    correction_account_move_id = fields.Many2one(
        comodel_name="account.move",
        string="Correction Journal Entry",
        copy=False,
        readonly=True,
        index="btree_not_null",
    )

    @api.constrains("amount")
    def _check_amount(self):
        blocked = self.filtered(
            lambda p: not p.is_payment_correction
            and not self.env.context.get("allow_pos_payment_correction")
            and (p.pos_order_id.state == "done" or p.pos_order_id.account_move)
        )
        if blocked:
            raise ValidationError(_("You cannot edit a payment for a posted order."))

    @api.constrains("payment_method_id")
    def _check_payment_method_id(self):
        to_check = self.filtered(
            lambda p: not p.is_payment_correction
            and not self.env.context.get("allow_pos_payment_correction")
        )
        if to_check:
            super(PosPayment, to_check)._check_payment_method_id()

    @api.constrains("is_payment_correction", "corrected_payment_ids", "pos_order_id")
    def _check_payment_correction_link(self):
        for payment in self:
            if not payment.is_payment_correction:
                if payment.corrected_payment_ids:
                    raise ValidationError(
                        _("Only fixing payments can be linked to wrong payments.")
                    )
                continue
            if not payment.corrected_payment_ids:
                raise ValidationError(
                    _("A fixing payment must be linked to at least one wrong payment.")
                )
            wrong = payment.corrected_payment_ids
            if wrong.filtered("is_payment_correction"):
                raise ValidationError(
                    _("You cannot link a fixing payment to another fixing payment.")
                )
            if wrong.filtered(lambda p: p.pos_order_id != payment.pos_order_id):
                raise ValidationError(
                    _("Wrong payments must belong to the same POS order.")
                )

    @api.onchange("is_payment_correction")
    def _onchange_is_payment_correction(self):
        if not self.is_payment_correction:
            self.corrected_payment_ids = [(5, 0, 0)]

    def _get_correction_receivable_account(self):
        """Resolve the receivable account the original POS session actually used.

        Priority:
        1. Session move line for this payment method (same account as POSS/...)
        2. Payment method Intermediary Account
        3. Session / company PoS receivable fallback
        """
        self.ensure_one()
        method = self.payment_method_id
        wrong = self.corrected_payment_ids[:1]
        session_move = self.pos_order_id.session_move_id

        if session_move and method:
            method_name = method.display_name or method.name or ""
            candidates = session_move.line_ids.filtered(
                lambda line: method_name and method_name in (line.name or "")
            )
            if candidates and wrong:
                # Wrong positive tender -> debit on receivable; change/negative -> credit
                if wrong.amount >= 0:
                    signed = candidates.filtered(lambda line: line.debit > 0)
                else:
                    signed = candidates.filtered(lambda line: line.credit > 0)
                pool = signed or candidates
                target = abs(wrong.amount)
                best = min(
                    pool,
                    key=lambda line: abs((line.debit or line.credit or 0.0) - target),
                )
                if best.account_id:
                    return best.account_id
            elif candidates and candidates[0].account_id:
                return candidates[0].account_id

        if method.receivable_account_id:
            return method.receivable_account_id

        session = self.session_id
        if session:
            return session._get_receivable_account(method)

        return self.company_id.account_default_pos_receivable_account_id
