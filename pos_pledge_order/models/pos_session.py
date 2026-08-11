# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)


class PosSession(models.Model):
    _inherit = "pos.session"

    @api.model
    def _load_pos_data_models(self, config):
        models_to_load = super()._load_pos_data_models(config)
        for model_name in ("pos.site.service.menu", "pos.site.service.product.line"):
            if model_name not in models_to_load:
                models_to_load.append(model_name)
                _logger.info(
                    "[SITE_SERVICE] Registered POS data model %s for config id=%s",
                    model_name,
                    config.id,
                )
        return models_to_load

    def get_session_orders(self):
        """Exclude legacy technical pledge orders from session aggregates."""
        orders = super().get_session_orders()
        return orders.filtered(lambda o: not o.is_pledge_generated)

    def _get_closed_orders(self):
        orders = super()._get_closed_orders()
        return orders.filtered(lambda o: not o.is_pledge_generated)

    def _get_pledge_session_summary(self):
        """Informational pledge totals for closing (no drawer adjustment)."""
        self.ensure_one()
        Pledge = self.env["pos.advance.order.pledge"].sudo()
        cur = self.currency_id

        collected = Pledge.search([
            ("state", "in", ("active", "returned")),
            ("receive_pos_session_id", "=", self.id),
        ])
        returned = Pledge.search([
            ("state", "=", "returned"),
            ("return_pos_session_id", "=", self.id),
        ])

        collected_total = sum(collected.mapped("pledge_subtotal"))
        returned_total = sum(returned.mapped("pledge_subtotal"))
        cash_returned = 0.0
        bank_returned = 0.0
        return_by_payment_method = {}
        for pl in returned:
            amt = pl.pledge_subtotal or 0.0
            pm = pl.return_payment_method_id
            if pm and pm.type == "cash":
                cash_returned += amt
            else:
                bank_returned += amt
            pm_key = pm.id if pm else 0
            pm_bucket = return_by_payment_method.setdefault(
                pm_key,
                {
                    "payment_method_id": pm.id if pm else False,
                    "payment_method_name": pm.display_name if pm else _("Unknown"),
                    "amount": 0.0,
                    "count": 0,
                },
            )
            pm_bucket["amount"] += amt
            pm_bucket["count"] += 1

        return_by_payment_method_list = [
            {
                **values,
                "amount": cur.round(values["amount"]),
            }
            for values in return_by_payment_method.values()
            if not cur.is_zero(values["amount"])
        ]
        return_by_payment_method_list.sort(
            key=lambda row: row.get("payment_method_name") or ""
        )

        return {
            "collected_count": len(collected),
            "collected_total": cur.round(collected_total),
            "returned_count": len(returned),
            "returned_total": cur.round(returned_total),
            "return_cash": cur.round(cash_returned),
            "return_bank": cur.round(bank_returned),
            "return_by_payment_method": return_by_payment_method_list,
        }

    def get_closing_control_data(self):
        data = super().get_closing_control_data()
        summary = self._get_pledge_session_summary()
        if summary["collected_count"] or summary["returned_count"]:
            data["pledge_completion_details"] = summary
            _logger.info(
                "[PLEDGE_CLOSING] session=%s(%s) informational pledge_summary=%s",
                self.name,
                self.id,
                summary,
            )
        return data
