import io
from datetime import date, datetime

from odoo import http
from odoo.http import request

try:
    import xlsxwriter
except Exception:
    xlsxwriter = None


class PackingListXlsxController(http.Controller):

    def _safe_str(self, v):
        if not v:
            return ""
        if isinstance(v, (date, datetime)):
            return v.strftime("%Y-%m-%d")
        return str(v)

    def _compute_lines(self, move):
        # reuse your existing base logic from models/report_packing_list.py
        base = request.env["report.ameen_anabtawi_packing_list.pl_base"].sudo()
        res = base._compute_from_pickings(move)
        if res is None:
            res = base._compute_from_invoice(move)
        return res.get("lines", []), res.get("totals", {})

    def _build_xlsx(self, move, show_dates):
        if not xlsxwriter:
            raise Exception("xlsxwriter library is not available on this server.")

        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {"in_memory": True})
        ws = wb.add_worksheet((move.name or "Packing List")[:31])

        # Formats
        fmt_title = wb.add_format({"bold": True, "font_size": 14, "align": "center"})
        fmt_head = wb.add_format({"bold": True, "border": 1, "align": "center", "valign": "vcenter"})
        fmt_cell = wb.add_format({"border": 1, "align": "center", "valign": "vcenter"})
        fmt_num = wb.add_format({"border": 1, "align": "center", "valign": "vcenter", "num_format": "0.00"})
        fmt_tot = wb.add_format({"bold": True, "border": 1, "align": "center", "valign": "vcenter", "num_format": "0.00"})

        # Column widths (matches your table)
        col_widths = [18, 10]  # Barcode, HS
        if show_dates:
            col_widths += [14, 14]  # Production, Expiry
        col_widths += [28, 10, 10, 12, 10, 10, 12, 14, 16]  # Product.. totals
        for i, w in enumerate(col_widths):
            ws.set_column(i, i, w)

        last_col = len(col_widths) - 1
        ws.merge_range(0, 0, 0, last_col, "Packing List" + (" (With Dates)" if show_dates else ""), fmt_title)

        # Header info
        ws.write(2, 0, "Company", fmt_head)
        ws.write(2, 1, move.company_id.name or "", fmt_cell)
        ws.write(3, 0, "Invoice No", fmt_head)
        ws.write(3, 1, move.name or "", fmt_cell)
        ws.write(4, 0, "Date", fmt_head)
        ws.write(4, 1, self._safe_str(move.invoice_date), fmt_cell)

        ws.write(2, last_col - 2, "Customer", fmt_head)
        ws.write(2, last_col - 1, move.partner_id.name or "", fmt_cell)
        ws.write(3, last_col - 2, "Email", fmt_head)
        ws.write(3, last_col - 1, move.partner_id.email or "", fmt_cell)

        # Table headers (your requested order)
        headers = ["Barcode", "HS Code"]
        if show_dates:
            headers += ["Production Date", "Expiry Date"]
        headers += [
            "Product",
            "Net Wt/Kg",
            "Gross Wt/Kg",
            "Pack Type",
            "Units",
            "Qty/Carton",
            "Total Cartons",
            "Total Net Wt/Kg",
            "Total Gross Wt/Kg",
        ]

        start_row = 6
        for c, h in enumerate(headers):
            ws.write(start_row, c, h, fmt_head)

        # Data
        lines, totals = self._compute_lines(move)
        r = start_row + 1

        for l in lines:
            c = 0
            ws.write(r, c, l.get("barcode", ""), fmt_cell); c += 1
            ws.write(r, c, l.get("hs_code", ""), fmt_cell); c += 1

            if show_dates:
                ws.write(r, c, self._safe_str(l.get("production_date")), fmt_cell); c += 1
                ws.write(r, c, self._safe_str(l.get("expiry_date")), fmt_cell); c += 1

            ws.write(r, c, l.get("product_name", ""), fmt_cell); c += 1
            ws.write_number(r, c, float(l.get("net_w", 0.0) or 0.0), fmt_num); c += 1
            ws.write_number(r, c, float(l.get("gross_w", 0.0) or 0.0), fmt_num); c += 1
            ws.write(r, c, l.get("package_type", ""), fmt_cell); c += 1
            ws.write_number(r, c, float(l.get("units", 0.0) or 0.0), fmt_num); c += 1
            ws.write_number(r, c, float(l.get("qty_per_carton", 0) or 0), fmt_num); c += 1
            ws.write_number(r, c, float(l.get("cartons", 0.0) or 0.0), fmt_num); c += 1
            ws.write_number(r, c, float(l.get("net_total", 0.0) or 0.0), fmt_num); c += 1
            ws.write_number(r, c, float(l.get("gross_total", 0.0) or 0.0), fmt_num); c += 1
            r += 1

        # Totals row
        label_cols = 6 if not show_dates else 8  # up to Pack Type
        ws.merge_range(r, 0, r, label_cols - 1, "Totals", fmt_head)

        units_col = label_cols
        ws.write_number(r, units_col, float(totals.get("tot_units", 0.0) or 0.0), fmt_tot)
        ws.write(r, units_col + 1, "", fmt_head)  # Qty/Carton blank
        ws.write_number(r, units_col + 2, float(totals.get("tot_cartons", 0.0) or 0.0), fmt_tot)
        ws.write_number(r, units_col + 3, float(totals.get("tot_net", 0.0) or 0.0), fmt_tot)
        ws.write_number(r, units_col + 4, float(totals.get("tot_gross", 0.0) or 0.0), fmt_tot)

        wb.close()
        output.seek(0)
        return output.read()

    @http.route("/packing_list/xlsx/<int:move_id>/<string:mode>", type="http", auth="user")
    def download_packing_list_xlsx(self, move_id, mode="nodate", **kwargs):
        move = request.env["account.move"].browse(move_id)
        if not move.exists():
            return request.not_found()

        move.check_access_rights("read")
        move.check_access_rule("read")

        show_dates = (mode == "date")
        content = self._build_xlsx(move, show_dates=show_dates)

        filename = f"Packing_List_{move.name or move_id}"
        if show_dates:
            filename += "_With_Dates"
        filename += ".xlsx"

        headers = [
            ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("Content-Disposition", f'attachment; filename="{filename}"'),
        ]
        return request.make_response(content, headers=headers)
