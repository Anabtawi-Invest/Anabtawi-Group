from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


class PosOrder(models.Model):
    _inherit = "pos.order"

    open_amount = fields.Monetary(copy=False, help="Extra POS adjustment applied without adding a negative order line.")

    @api.model
    def _load_pos_data_fields(self, config):
        fields_to_load = super()._load_pos_data_fields(config)
        if fields_to_load and "open_amount" not in fields_to_load:
            fields_to_load.append("open_amount")
        return fields_to_load

    def _get_open_amount_label(self):
        self.ensure_one()
        return _("Open Amount")

    def _get_open_amount_account(self):
        self.ensure_one()
        product = self.config_id.discount_adjustment_product_id
        if not product:
            raise UserError(_("Please configure Discount Adjustment Product in POS settings."))

        account = product.with_company(self.company_id)._get_product_accounts()["income"]
        if self.fiscal_position_id:
            account = self.fiscal_position_id.map_account(account)
        if not account:
            raise UserError(
                _("Please define an income/liability account for the POS adjustment product '%s'.")
                % product.display_name
            )
        return account

    def _prepare_open_amount_adjustment_vals(self, invoice):
        self.ensure_one()
        open_amount = abs(self.open_amount)
        if not open_amount:
            return {}

        rate = invoice.invoice_currency_rate
        difference_currency = -invoice.direction_sign * open_amount
        difference_balance = (
            invoice.company_currency_id.round(difference_currency / rate) if rate else 0.0
        )
        return {
            "name": self._get_open_amount_label(),
            "amount_currency": difference_currency,
            "balance": difference_balance,
            "currency_id": invoice.currency_id.id,
            "display_type": "rounding",
            "account_id": self._get_open_amount_account().id,
            "is_pos_open_amount": True,
        }

    def _create_invoice(self, move_vals):
        invoice = super()._create_invoice(move_vals)
        open_amount_orders = self.filtered(lambda order: not order.currency_id.is_zero(order.open_amount))
        if not open_amount_orders:
            return invoice

        payment_term_line = (
            invoice.line_ids.filtered(lambda line: line.display_type == "payment_term")
            .sorted(lambda line: -abs(line.amount_currency))[:1]
        )
        if not payment_term_line:
            raise UserError(_("The invoice does not contain a payment term line to offset Open Amount."))

        grouped_adjustments = {}
        total_amount_currency = 0.0
        total_balance = 0.0
        for order in open_amount_orders:
            adjustment_vals = order._prepare_open_amount_adjustment_vals(invoice)
            if not adjustment_vals:
                continue
            total_amount_currency += adjustment_vals["amount_currency"]
            total_balance += adjustment_vals["balance"]
            account_id = adjustment_vals["account_id"]
            grouped_vals = grouped_adjustments.setdefault(account_id, adjustment_vals)
            if grouped_vals is not adjustment_vals:
                grouped_vals["amount_currency"] += adjustment_vals["amount_currency"]
                grouped_vals["balance"] += adjustment_vals["balance"]

        commands = [Command.create(vals) for vals in grouped_adjustments.values()]
        commands.append(
            Command.update(
                payment_term_line.id,
                {
                    "amount_currency": payment_term_line.amount_currency - total_amount_currency,
                    "balance": payment_term_line.balance - total_balance,
                },
            )
        )
        if commands:
            with self.env["account.move"]._check_balanced({"records": invoice}):
                invoice.with_context(skip_invoice_sync=True).line_ids = commands
        return invoice
