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

        def _append_pledge_payment(name, total, sess_id):
            result["payments"].append({
                "name": name,
                "session": sess_id,
                "total": total,
                "final_count": total,
                "money_counted": total,
                "money_difference": 0.0,
                "cash_moves": [],
                "count": True,
            })

        for session in sessions:
            summary = session._get_pledge_deposit_closing_summary()
            cur = session.currency_id
            cash_in = summary.get("cash_in") or 0.0
            cash_out = summary.get("cash_out") or 0.0
            if not cur.is_zero(cash_in):
                _append_pledge_payment(
                    _("Cash pledge (deposit) %s") % session.name,
                    cash_in,
                    session.id,
                )
            if not cur.is_zero(cash_out):
                _append_pledge_payment(
                    _("Cash pledge (return / cash out) %s") % session.name,
                    -cash_out,
                    session.id,
                )
            by_in = summary.get("by_pm_in") or {}
            by_out = summary.get("by_pm_out") or {}
            for pm_id in set(by_in) | set(by_out):
                pin = by_in.get(pm_id, 0.0)
                pout = by_out.get(pm_id, 0.0)
                pm = self.env["pos.payment.method"].sudo().browse(pm_id)
                label = pm.exists() and pm.name or _("Payment method")
                if not cur.is_zero(pin):
                    _append_pledge_payment(
                        _("Pledge deposit (%s) — %s") % (label, session.name),
                        pin,
                        session.id,
                    )
                if not cur.is_zero(pout):
                    _append_pledge_payment(
                        _("Pledge return / cash out (%s) — %s") % (label, session.name),
                        -pout,
                        session.id,
                    )
        return result
