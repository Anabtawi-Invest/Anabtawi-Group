from datetime import datetime, time

import pytz

from odoo import fields, models


class ReportDeliveryTransaction(models.AbstractModel):
    _name = "report.inventory_delivery_transaction_report.report_delivery_transaction"
    _description = "Delivery Transaction Report"

    def _get_report_values(self, docids, data=None):
        data = data or {}
        report_date = fields.Date.to_date(data.get("report_date"))
        location_id = data.get("location_id")
        location = self.env["stock.location"].browse(location_id) if location_id else False

        user_tz = pytz.timezone(self.env.user.tz or "UTC")
        until_local = user_tz.localize(datetime.combine(report_date, time.max))
        until_datetime = until_local.astimezone(pytz.UTC).replace(tzinfo=None)
        domain = [
            ("state", "in", ("paid", "done", "invoiced")),
            ("date_order", "<=", fields.Datetime.to_string(until_datetime)),
        ]
        if location:
            domain.append(("picking_type_id.default_location_src_id", "child_of", location.id))

        orders = self.env["pos.order"].search(domain, order="date_order asc, id asc")
        currency = orders[:1].currency_id or self.env.company.currency_id

        lines = []
        total_tender = 0.0
        for order in orders:
            order_location = order.picking_type_id.default_location_src_id
            payment_methods = ", ".join(order.payment_ids.mapped("payment_method_id.name")) or "-"
            tender_total = order.amount_total or 0.0
            total_tender += tender_total
            lines.append(
                {
                    "location_name": order_location.display_name or "-",
                    "transaction_time": order.date_order,
                    "employee_name": order.user_id.name or "-",
                    "reference_info": payment_methods,
                    "tender_total": tender_total,
                }
            )

        return {
            "doc_ids": docids,
            "doc_model": "delivery.transaction.report.wizard",
            "docs": self.env["delivery.transaction.report.wizard"].browse(docids),
            "report_date": report_date,
            "selected_location": location.display_name if location else "All",
            "lines": lines,
            "total_tender": total_tender,
            "currency": currency,
            "company": self.env.company,
        }
