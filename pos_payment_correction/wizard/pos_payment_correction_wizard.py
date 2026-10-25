from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare, float_is_zero, float_round


class PosPaymentCorrectionWizard(models.TransientModel):
    _name = "pos.payment.correction.wizard"
    _description = "POS Payment Correction Wizard"

    order_id = fields.Many2one(
        comodel_name="pos.order",
        string="POS Order",
        required=True,
        readonly=True,
    )
    company_id = fields.Many2one(related="order_id.company_id")
    currency_id = fields.Many2one(related="order_id.currency_id")
    amount_total = fields.Monetary(
        related="order_id.amount_total",
        currency_field="currency_id",
    )
    line_ids = fields.One2many(
        comodel_name="pos.payment.correction.wizard.line",
        inverse_name="wizard_id",
        string="Payments to Correct",
    )
    create_account_move = fields.Boolean(
        string="Create Accounting Entry",
        default=True,
        help="Post a miscellaneous journal entry that offsets the intermediary "
        "POS receivable accounts impacted by the wrong payments.",
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Journal",
        domain="[('company_id', '=', company_id), ('type', '=', 'general')]",
        check_company=True,
    )
    accounting_date = fields.Date(
        string="Accounting Date",
        default=fields.Date.context_today,
    )
    note = fields.Char(
        string="Reference / Note",
        help="Shown on the correction payments and journal entry.",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        order = self.env["pos.order"].browse(
            res.get("order_id") or self.env.context.get("default_order_id")
        )
        if order:
            res["order_id"] = order.id
            res["note"] = _("Correct POS %(order)s (payment fix)", order=order.name)
            res["accounting_date"] = fields.Date.to_date(order.date_order) or fields.Date.context_today(
                self
            )
            journal = self._default_misc_journal(order.company_id)
            if journal:
                res["journal_id"] = journal.id
            if "line_ids" in fields_list or not fields_list:
                lines = []
                for payment in order.payment_ids.filtered(
                    lambda p: not p.is_payment_correction
                ).sorted("id"):
                    lines.append(
                        (
                            0,
                            0,
                            {
                                "payment_id": payment.id,
                                "correct_amount": payment.amount,
                            },
                        )
                    )
                res["line_ids"] = lines
        return res

    @api.model
    def _default_misc_journal(self, company):
        Journal = self.env["account.journal"].sudo()
        journal = Journal.search(
            [
                ("company_id", "=", company.id),
                ("type", "=", "general"),
                ("code", "=", "MISC1"),
            ],
            limit=1,
        )
        if not journal:
            journal = Journal.search(
                [
                    ("company_id", "=", company.id),
                    ("type", "=", "general"),
                ],
                order="sequence, id",
                limit=1,
            )
        return journal

    def action_confirm(self):
        self.ensure_one()
        if not self.env.user.has_group("pos_payment_correction.group_pos_payment_correction"):
            raise UserError(_("You are not allowed to correct POS payments."))

        order = self.order_id
        active_lines = self.line_ids.filtered(
            lambda l: float_compare(
                l.correction_amount,
                0.0,
                precision_rounding=order.currency_id.rounding,
            )
            != 0
        )
        if not active_lines:
            raise UserError(
                _("Set at least one Correct Amount different from the current amount.")
            )

        if self.create_account_move and not self.journal_id:
            raise UserError(
                _("Please select a miscellaneous journal for the accounting entry.")
            )

        Payment = self.env["pos.payment"].sudo().with_context(allow_pos_payment_correction=True)
        created_payments = Payment
        for line in active_lines:
            created_payments |= Payment.create(
                {
                    "pos_order_id": order.id,
                    "payment_method_id": line.payment_method_id.id,
                    "amount": line.correction_amount,
                    "payment_date": fields.Datetime.now(),
                    "is_payment_correction": True,
                    "is_change": line.payment_id.is_change and line.correction_amount < 0,
                    "corrected_payment_ids": [(6, 0, line.payment_id.ids)],
                    "name": self.note or _("Payment correction"),
                }
            )

        amount_paid = sum(order.payment_ids.mapped("amount"))
        amount_return = order._get_payment_correction_amount_return()
        order.write(
            {
                "amount_paid": amount_paid,
                "amount_return": amount_return,
                "amount_difference": amount_paid - order.amount_total,
            }
        )

        if float_compare(
            amount_paid, order.amount_total, precision_rounding=order.currency_id.rounding
        ) != 0:
            raise UserError(
                _(
                    "After correction, payments (%(paid)s) do not equal order total (%(total)s). "
                    "Adjust the correct amounts so the net matches the order total.",
                    paid=amount_paid,
                    total=order.amount_total,
                )
            )

        account_move = self.env["account.move"]
        accounting_note = False
        if self.create_account_move:
            account_move, accounting_note = self._create_correction_account_move(
                created_payments
            )
            if account_move:
                created_payments.write({"correction_account_move_id": account_move.id})

        body = _(
            "POS payment correction created %(count)s fixing payment(s).",
            count=len(created_payments),
        )
        if account_move:
            body = _(
                "%(body)s Accounting entry: %(move)s.",
                body=body,
                move=account_move._get_html_link(),
            )
        elif accounting_note:
            body = "%s %s" % (body, accounting_note)
        order.message_post(body=body)

        message = _(
            "%(count)s fixing payment(s) added on %(order)s.",
            count=len(created_payments),
            order=order.name,
        )
        if account_move:
            message = _(
                "%(msg)s Entry %(move)s posted.",
                msg=message,
                move=account_move.name,
            )
        elif accounting_note:
            message = "%s %s" % (message, accounting_note)

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Payments corrected"),
                "message": message,
                "type": "success",
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    def _create_correction_account_move(self, correction_payments):
        """Create JE with one line per fixing payment (no netting to empty).

        Returns (move, skip_note).
        """
        self.ensure_one()
        order = self.order_id
        currency = order.currency_id
        company = order.company_id
        line_commands = []
        base_label = self.note or _("Correct POS %(order)s", order=order.name)

        for payment in correction_payments:
            account = payment._get_correction_receivable_account()
            if not account:
                raise UserError(
                    _(
                        "No intermediary / PoS receivable account found for payment method %(method)s.",
                        method=payment.payment_method_id.display_name,
                    )
                )
            amount = float_round(payment.amount, precision_rounding=currency.rounding)
            if float_is_zero(amount, precision_rounding=currency.rounding):
                continue
            label = "%s - %s" % (base_label, payment.payment_method_id.display_name)
            # Positive fixing => debit receivable; negative fixing => credit receivable
            if amount > 0:
                line_commands.append(
                    (
                        0,
                        0,
                        {
                            "account_id": account.id,
                            "name": label,
                            "debit": amount,
                            "credit": 0.0,
                        },
                    )
                )
            else:
                line_commands.append(
                    (
                        0,
                        0,
                        {
                            "account_id": account.id,
                            "name": label,
                            "debit": 0.0,
                            "credit": abs(amount),
                        },
                    )
                )

        if not line_commands:
            return self.env["account.move"], _(
                "No accounting entry: fixing amounts were zero."
            )

        debit = sum(cmd[2].get("debit", 0.0) for cmd in line_commands)
        credit = sum(cmd[2].get("credit", 0.0) for cmd in line_commands)
        if float_compare(debit, credit, precision_rounding=currency.rounding) != 0:
            raise UserError(
                _(
                    "Correction accounting entry is unbalanced (debit %(debit)s / credit %(credit)s). "
                    "Correct amounts that net across payment methods, or post the entry manually.",
                    debit=debit,
                    credit=credit,
                )
            )

        account_ids = {cmd[2]["account_id"] for cmd in line_commands}
        if len(account_ids) == 1 and float_compare(debit, credit, precision_rounding=currency.rounding) == 0:
            # Same account on both sides = wash entry (what happened with 114002/114002)
            raise UserError(
                _(
                    "Cannot post accounting correction: all fixing lines resolved to the same "
                    "receivable account. Check each payment method's Intermediary Account "
                    "(صندوق should differ from طلبات, e.g. 114001 vs 114002), or post the "
                    "journal entry manually."
                )
            )

        move = (
            self.env["account.move"]
            .sudo()
            .create(
                {
                    "move_type": "entry",
                    "journal_id": self.journal_id.id,
                    "company_id": company.id,
                    "date": self.accounting_date,
                    "ref": self.note or _("Correct POS %s", order.name),
                    "narration": _(
                        "Automatic POS payment correction for order %(order)s (id %(order_id)s). "
                        "Original wrong payments kept; fixing payments linked for audit.",
                        order=order.name,
                        order_id=order.id,
                    ),
                    "line_ids": line_commands,
                }
            )
        )
        move.action_post()
        return move, False


class PosPaymentCorrectionWizardLine(models.TransientModel):
    _name = "pos.payment.correction.wizard.line"
    _description = "POS Payment Correction Wizard Line"

    wizard_id = fields.Many2one(
        comodel_name="pos.payment.correction.wizard",
        required=True,
        ondelete="cascade",
    )
    payment_id = fields.Many2one(
        comodel_name="pos.payment",
        string="Wrong Payment",
        required=True,
        ondelete="cascade",
    )
    payment_method_id = fields.Many2one(
        related="payment_id.payment_method_id",
        string="Payment Method",
    )
    payment_date = fields.Datetime(related="payment_id.payment_date")
    currency_id = fields.Many2one(related="wizard_id.currency_id")
    current_amount = fields.Monetary(
        related="payment_id.amount",
        string="Current Amount",
        currency_field="currency_id",
    )
    correct_amount = fields.Monetary(
        string="Correct Amount",
        required=True,
        currency_field="currency_id",
        help="What this payment method amount should have been.",
    )
    correction_amount = fields.Monetary(
        string="Fixing Amount",
        compute="_compute_correction_amount",
        currency_field="currency_id",
        help="Payment line that will be created (correct − current).",
    )

    @api.depends("current_amount", "correct_amount")
    def _compute_correction_amount(self):
        for line in self:
            line.correction_amount = (line.correct_amount or 0.0) - (line.current_amount or 0.0)
