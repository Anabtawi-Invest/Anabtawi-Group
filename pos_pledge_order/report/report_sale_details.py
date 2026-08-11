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

        def _append_pledge_line(name, total, sess_id):
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
            summary = session._get_pledge_session_summary()
            cur = session.currency_id
            collected = summary.get("collected_total") or 0.0
            returned = summary.get("returned_total") or 0.0
            if not cur.is_zero(collected):
                _append_pledge_line(
                    _("Pledges collected (info) %s") % session.name,
                    collected,
                    session.id,
                )
            if not cur.is_zero(returned):
                return_rows = summary.get("return_by_payment_method") or []
                if return_rows:
                    for row in return_rows:
                        pm_name = row.get("payment_method_name") or _("Unknown")
                        amount = row.get("amount") or 0.0
                        count = row.get("count") or 0
                        label = pm_name
                        if count > 1:
                            label = _("%(method)s (%(count)s pledges)") % {
                                "method": pm_name,
                                "count": count,
                            }
                        _append_pledge_line(
                            _("Pledge return: %(label)s — %(session)s")
                            % {"label": label, "session": session.name},
                            -amount,
                            session.id,
                        )
                else:
                    _append_pledge_line(
                        _("Pledges returned (info) %s") % session.name,
                        -returned,
                        session.id,
                    )
        return result
