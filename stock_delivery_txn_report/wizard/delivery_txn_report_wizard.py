from datetime import datetime, time
import io

import pytz

from odoo import _, fields, models


class DeliveryTxnReportWizard(models.TransientModel):
    _name = "delivery.txn.report.wizard"
    _description = "Delivery Transactions Report Wizard"

    report_date = fields.Date(
        string="Until Date",
        required=True,
        default=fields.Date.context_today,
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Location",
        domain="[('usage', '=', 'internal')]",
        help="Leave empty to include all locations.",
    )

    def _get_orders(self):
        self.ensure_one()
        user_tz = pytz.timezone(self.env.user.tz or "UTC")
        until_local = user_tz.localize(datetime.combine(self.report_date, time.max))
        until_utc = until_local.astimezone(pytz.UTC).replace(tzinfo=None)
        domain = [
            ("state", "in", ("paid", "done", "invoiced")),
            ("date_order", "<=", fields.Datetime.to_string(until_utc)),
        ]
        if self.location_id:
            domain.append(
                ("picking_type_id.default_location_src_id", "child_of", self.location_id.id)
            )
        return self.env["pos.order"].search(domain, order="date_order asc, id asc")

    def _generate_xlsx_content(self):
        self.ensure_one()
        import xlsxwriter  # pylint: disable=import-outside-toplevel

        orders = self._get_orders()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet(_("Deliveries"))

        title_style = workbook.add_format({"bold": True, "bg_color": "#F26D6D", "border": 1})
        info_label = workbook.add_format({"border": 1})
        info_value = workbook.add_format({"border": 1})
        header_style = workbook.add_format({"bold": True, "border": 1, "bg_color": "#E6E6E6"})
        text_style = workbook.add_format({"border": 1})
        datetime_style = workbook.add_format({"border": 1, "num_format": "m/d/yyyy h:mm AM/PM"})
        amount_style = workbook.add_format(
            {"border": 1, "num_format": "#,##0.00", "align": "right"}
        )
        total_style = workbook.add_format(
            {"border": 1, "bold": True, "num_format": "#,##0.00", "align": "right"}
        )

        sheet.set_column("A:A", 20)
        sheet.set_column("B:B", 24)
        sheet.set_column("C:C", 24)
        sheet.set_column("D:D", 28)
        sheet.set_column("E:E", 14)

        sheet.write("A1", _("Deliveries"), title_style)
        sheet.write("A3", _("Business Dates"), info_label)
        sheet.write("B3", fields.Date.to_string(self.report_date), info_value)
        sheet.write("A4", _("Locations"), info_label)
        sheet.write("B4", self.location_id.display_name if self.location_id else _("All"), info_value)
        sheet.write("A5", _("Revenue Centers"), info_label)
        sheet.write("B5", _("All"), info_value)
        sheet.write("A6", _("Order Types"), info_label)
        sheet.write("B6", _("All"), info_value)

        start_row = 7
        headers = [
            _("Location"),
            _("TransactionTime"),
            _("Employee"),
            _("ReferenceInfo"),
            _("TenderTotal"),
        ]
        for col, header in enumerate(headers):
            sheet.write(start_row, col, header, header_style)

        total_amount = sum(orders.mapped("amount_total"))
        row = start_row + 1
        sheet.write(row, 0, _("Delivery Amount"), text_style)
        sheet.write_number(row, 4, total_amount, total_style)
        row += 1

        for order in orders:
            location = order.picking_type_id.default_location_src_id.display_name or "-"
            methods = ", ".join(order.payment_ids.mapped("payment_method_id.name")) or "-"
            sheet.write(row, 0, location, text_style)
            sheet.write_datetime(
                row,
                1,
                fields.Datetime.context_timestamp(self, order.date_order),
                datetime_style,
            )
            sheet.write(row, 2, order.user_id.name or "-", text_style)
            sheet.write(row, 3, methods, text_style)
            sheet.write_number(row, 4, order.amount_total or 0.0, amount_style)
            row += 1

        workbook.close()
        return output.getvalue()

    def action_print_excel(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": f"/stock_delivery_txn_report/xlsx/{self.id}",
            "target": "self",
        }
