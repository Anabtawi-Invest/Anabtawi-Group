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
        self.ensure_one()
        session = self.session_id
        if session:
            return session._get_receivable_account(self.payment_method_id)
        return (
            self.payment_method_id.receivable_account_id
            or self.company_id.account_default_pos_receivable_account_id
        )
