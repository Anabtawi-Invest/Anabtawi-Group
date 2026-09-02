from odoo import api, models


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
                    ("start_at", ">=", result["date_start"]),
                    ("stop_at", "<=", result["date_stop"]),
                ])
        else:
            sessions = self.env["pos.session"].search([("id", "in", session_ids or [])])

        for session in sessions:
            summary = session._get_advance_summary()
            if summary["cash"]:
                result["payments"].append({
                    "name": "Cash Advance %s" % session.name,
                    "session": session.id,
                    "total": summary["cash"],
                    "final_count": summary["cash"],
                    "money_counted": summary["cash"],
                    "money_difference": 0.0,
                    "cash_moves": [],
                    "count": True,
                })
            if summary["bank"]:
                result["payments"].append({
                    "name": "Bank Advance %s" % session.name,
                    "session": session.id,
                    "total": summary["bank"],
                    "final_count": summary["bank"],
                    "money_counted": summary["bank"],
                    "money_difference": 0.0,
                    "cash_moves": [],
                    "count": True,
                })
        return result
