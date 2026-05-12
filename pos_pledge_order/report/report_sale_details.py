# -*- coding: utf-8 -*-
from odoo import _, api, models


class ReportPointOfSaleSaleDetails(models.AbstractModel):
    _inherit = "report.point_of_sale.report_saledetails"

    @api.model
    def get_sale_details(self, date_start=False, date_stop=False, config_ids=False, session_ids=False, **kwargs):
        result = super().get_sale_details(
            date_start=date_start,
            date_stop=date_stop,
            config_ids=config_ids,
            session_ids=session_ids,
            **kwargs,
        )

        if config_ids:
            sessions = self.env["pos.session"].search([("id", "in", session_ids or [])])
            if not sessions:
                sessions = self.env["pos.session"].search([
                    ("config_id", "in", config_ids),
                    ("start_at", ">=", result.get("date_start")),
                    ("stop_at", "<=", result.get("date_stop")),
                ])
        else:
            sessions = self.env["pos.session"].search([("id", "in", session_ids or [])])

        for session in sessions:
            summary = session._get_pledge_deposit_closing_summary()
            cur = session.currency_id
            cash = summary.get("cash") or 0.0
            if not cur.is_zero(cash):
                if cash > 0:
                    pay_name = _("Cash pledge (deposit) %s") % session.name
                else:
                    pay_name = _("Cash pledge (return / cash out) %s") % session.name
                result["payments"].append({
                    "name": pay_name,
                    "session": session.id,
                    "total": cash,
                    "final_count": cash,
                    "money_counted": cash,
                    "money_difference": 0.0,
                    "cash_moves": [],
                    "count": True,
                })
            for pm_id, amt in (summary.get("by_pm") or {}).items():
                if cur.is_zero(amt or 0.0):
                    continue
                pm = self.env["pos.payment.method"].sudo().browse(pm_id)
                label = pm.exists() and pm.name or _("Payment method")
                if amt > 0:
                    pay_name = _("Pledge deposit (%s) — %s") % (label, session.name)
                else:
                    pay_name = _("Pledge return / cash out (%s) — %s") % (label, session.name)
                result["payments"].append({
                    "name": pay_name,
                    "session": session.id,
                    "total": amt,
                    "final_count": amt,
                    "money_counted": amt,
                    "money_difference": 0.0,
                    "cash_moves": [],
                    "count": True,
                })
        return result
