# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class PosConfig(models.Model):
    _inherit = "pos.config"

    @api.constrains("enable_advance_order", "pos_advance_receivable_account_id")
    def _check_advance_receivable_account(self):
        for cfg in self:
            if cfg.enable_advance_order and not cfg.pos_advance_receivable_account_id:
                raise ValidationError(
                    _(
                        "When Advance Order is enabled, you must set "
                        "'POS Advance Receivable Account' on this POS configuration."
                    )
                )

    enable_advance_order = fields.Boolean(string="Enable Advance Order")
    advance_order_manager_id = fields.Many2one(
        "res.users",
        string="Advance Orders Manager",
        help="This user will receive an email notification when an advance order payment is created.",
    )
    advance_notification_user_ids = fields.Many2many(
        "res.users",
        "pos_config_advance_notification_user_rel",
        "config_id",
        "user_id",
        string="Advance Notification Users",
        help="Users who will receive inbox notifications and emails when an advance order payment is created.",
    )

    pos_advance_account_id = fields.Many2one(
        "account.account",
        string="POS Advance Account",
        domain="[('account_type', '=', 'liability_current')]",
        help="Liability account for customer advance payments",
    )
    pos_advance_receivable_account_id = fields.Many2one(
        "account.account",
        string="POS Advance Receivable Account",
        domain="[('account_type', '=', 'asset_receivable')]",
        help="Receivable account used for Customer Account (pay later) on advance completion and for settlement entries. "
        "Required when Advance Order is enabled on this POS.",
    )

    pos_cash_journal_id = fields.Many2one(
        "account.journal",
        string="POS Cash Journal",
        domain="[('type', 'in', ('cash', 'bank'))]",
        help="Journal for cash advance payments",
    )

    pos_card_journal_id = fields.Many2one(
        "account.journal",
        string="POS Card Journal",
        domain="[('type', 'in', ('cash', 'bank'))]",
        help="Journal for card/bank advance payments",
    )

    pos_profit_account_id = fields.Many2one(
        "account.account",
        string="POS Profit Account",
        domain="[('account_type', 'in', ('income', 'income_other'))]",
        help="Income/Profit account used when posting the remaining payment (full total) for advance orders.",
    )

    advance_deposit_product_id = fields.Many2one(
        "product.product",
        string="Advance Deposit Product",
        domain=[("sale_ok", "=", True)],
        help="Product used to record customer advance as a POS sale line. Its income account should be a liability (Customer Deposits).",
    )
    pledge_product_id = fields.Many2one(
        "product.product",
        string="Pledge Product",
        domain=[("sale_ok", "=", True)],
        help="Product used to record pledge amount as a POS sale line. Its income account should be a liability.",
    )
    pos_pledge_liability_account_id = fields.Many2one(
        "account.account",
        string="Pledge Liability Account",
        domain="[('account_type', '=', 'liability_current')]",
        help="Account debited when applying pledge to receivable at sale completion. "
        "If empty, the pledge product income account is used (must match POS pledge postings).",
    )

