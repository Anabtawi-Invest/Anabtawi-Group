from odoo import models, fields, _
from odoo.exceptions import UserError

class PosAdvancePayment(models.Model):
    _name = "pos.advance.payment"

    order_id = fields.Many2one("pos.advance.order", required=True)
    amount = fields.Monetary(required=True)
    currency_id = fields.Many2one("res.currency", related="order_id.currency_id")
    journal_id = fields.Many2one("account.journal", required=True)
    move_id = fields.Many2one("account.move")

    def action_post(self):
        self.ensure_one()

        if self.amount <= 0:
            raise UserError(_("Amount must be positive"))

        config = self.order_id.pos_config_id
        liability = config.advance_liability_account_id

        if not liability:
            raise UserError(_("Missing Advance Liability Account"))

        journal_account = self.journal_id.default_account_id

        move = self.env["account.move"].create({
            "move_type": "entry",
            "journal_id": self.journal_id.id,
            "line_ids": [
                (0, 0, {
                    "account_id": journal_account.id,
                    "debit": self.amount,
                }),
                (0, 0, {
                    "account_id": liability.id,
                    "credit": self.amount,
                }),
            ],
        })

        move.action_post()
        self.move_id = move.id
