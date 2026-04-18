from odoo import _, api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    @api.depends_context("lang")
    @api.depends(
        "invoice_line_ids.currency_rate",
        "invoice_line_ids.tax_base_amount",
        "invoice_line_ids.tax_line_id",
        "invoice_line_ids.price_total",
        "invoice_line_ids.price_subtotal",
        "invoice_payment_term_id",
        "partner_id",
        "currency_id",
        "line_ids.amount_currency",
        "line_ids.balance",
        "line_ids.is_pos_open_amount",
    )
    def _compute_tax_totals(self):
        super()._compute_tax_totals()
        for move in self:
            if not move.tax_totals:
                continue

            open_amount_lines = move.line_ids.filtered("is_pos_open_amount")
            if not open_amount_lines:
                move.tax_totals.pop("pos_open_amount_currency", None)
                move.tax_totals.pop("pos_open_amount", None)
                move.tax_totals.pop("pos_open_amount_label", None)
                continue

            amount_currency = sum(open_amount_lines.mapped("amount_currency"))
            amount_company = sum(open_amount_lines.mapped("balance"))

            move.tax_totals["pos_open_amount_label"] = _("Open Amount")
            move.tax_totals["pos_open_amount_currency"] = amount_currency
            move.tax_totals["pos_open_amount"] = amount_company
            move.tax_totals["total_amount_currency"] += amount_currency
            move.tax_totals["total_amount"] += amount_company


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    is_pos_open_amount = fields.Boolean(copy=False)
