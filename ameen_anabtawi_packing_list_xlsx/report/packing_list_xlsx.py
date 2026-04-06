from odoo import models


class PackingListXlsxBase(models.AbstractModel):
    _name = "report.ameen_anabtawi_packing_list_xlsx.pl_xlsx_base"
    _description = "Packing List XLSX Base"

    def _get_data(self, moves):
        """
        Reuse the same base computation you already have in your main module:
        report.ameen_anabtawi_packing_list.pl_base
        """
        base = self.env["report.ameen_anabtawi_packing_list.pl_base"]

        result = {}
        for move in moves:
            res = base._compute_from_pickings(move)
            if res is None:
                res = base._compute_from_invoice(move)
            result[move.id] = res
        return result

    def _write_header(self, sheet, row, col, show_dates, fmt_header):
        headers = [
            "Barcode",
            "HS Code",
        ]
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

        for i, h in enumerate(headers):
            sheet.write(row, col + i, h, fmt_header)

        return len(headers)

    def _set_columns(self, sheet, show_dates):
        # widths tuned to look like your PDF
        widths = [18, 10]  # Barcode, HS
        if show_dates:
            widths += [14, 14]  # Prod, Exp
        widths += [25, 10, 10, 12, 10, 10, 12, 14, 16]  # remaining

        for idx, w in enumerate(widths):
            sheet.set_column(idx, idx, w)


class PackingListXlsxNoDates(models.AbstractModel):
    _name = "report.ameen_anabtawi_packing_list_xlsx.pl_xlsx_nodate"
    _inherit = "report.report_xlsx.abstract"
    _description = "Packing List XLSX (No Dates)"

    def generate_xlsx_report(self, workbook, data, moves):
        base = self.env["report.ameen_anabtawi_packing_list_xlsx.pl_xlsx_base"]
        computed = base._get_data(moves)

        fmt_title = workbook.add_format({"bold": True, "font_size": 14, "align": "center"})
        fmt_header = workbook.add_format({"bold": True, "border": 1, "align": "center", "valign": "vcenter"})
        fmt_cell = workbook.add_format({"border": 1, "align": "center", "valign": "vcenter"})
        fmt_num = workbook.add_format({"border": 1, "align": "center", "valign": "vcenter", "num_format": "0.00"})
        fmt_tot = workbook.add_format({"bold": True, "border": 1, "align": "center", "valign": "vcenter", "num_format": "0.00"})

        for move in moves:
            sheet = workbook.add_worksheet((move.name or "Packing List")[:31])

            base._set_columns(sheet, show_dates=False)

            sheet.merge_range(0, 0, 0, 12, "Packing List", fmt_title)

            # meta (similar to PDF header)
            sheet.write(2, 0, "Company", fmt_header)
            sheet.write(2, 1, move.company_id.name or "", fmt_cell)
            sheet.write(3, 0, "Invoice No", fmt_header)
            sheet.write(3, 1, move.name or "", fmt_cell)
            sheet.write(4, 0, "Date", fmt_header)
            sheet.write(4, 1, str(move.invoice_date or ""), fmt_cell)

            sheet.write(2, 9, "Customer", fmt_header)
            sheet.write(2, 10, move.partner_id.name or "", fmt_cell)
            sheet.write(3, 9, "Email", fmt_header)
            sheet.write(3, 10, move.partner_id.email or "", fmt_cell)

            start_row = 6
            col_count = base._write_header(sheet, start_row, 0, show_dates=False, fmt_header=fmt_header)

            row = start_row + 1
            res = computed.get(move.id, {})
            lines = res.get("lines", [])
            totals = res.get("totals", {})

            for l in lines:
                c = 0
                sheet.write(row, c, l.get("barcode", ""), fmt_cell); c += 1
                sheet.write(row, c, l.get("hs_code", ""), fmt_cell); c += 1

                sheet.write(row, c, l.get("product_name", ""), fmt_cell); c += 1
                sheet.write_number(row, c, float(l.get("net_w", 0.0)), fmt_num); c += 1
                sheet.write_number(row, c, float(l.get("gross_w", 0.0)), fmt_num); c += 1
                sheet.write(row, c, l.get("package_type", ""), fmt_cell); c += 1
                sheet.write_number(row, c, float(l.get("units", 0.0)), fmt_num); c += 1
                sheet.write_number(row, c, float(l.get("qty_per_carton", 0) or 0), fmt_num); c += 1
                sheet.write_number(row, c, float(l.get("cartons", 0.0)), fmt_num); c += 1
                sheet.write_number(row, c, float(l.get("net_total", 0.0)), fmt_num); c += 1
                sheet.write_number(row, c, float(l.get("gross_total", 0.0)), fmt_num); c += 1
                row += 1

            # Totals row
            sheet.merge_range(row, 0, row, 5, "Totals", fmt_header)
            sheet.write_number(row, 6, float(totals.get("tot_units", 0.0)), fmt_tot)
            sheet.write(row, 7, "", fmt_header)  # Qty/Carton total not meaningful
            sheet.write_number(row, 8, float(totals.get("tot_cartons", 0.0)), fmt_tot)
            sheet.write_number(row, 9, float(totals.get("tot_net", 0.0)), fmt_tot)
            sheet.write_number(row, 10, float(totals.get("tot_gross", 0.0)), fmt_tot)


class PackingListXlsxWithDates(models.AbstractModel):
    _name = "report.ameen_anabtawi_packing_list_xlsx.pl_xlsx_date"
    _inherit = "report.report_xlsx.abstract"
    _description = "Packing List XLSX (With Dates)"

    def generate_xlsx_report(self, workbook, data, moves):
        base = self.env["report.ameen_anabtawi_packing_list_xlsx.pl_xlsx_base"]
        computed = base._get_data(moves)

        fmt_title = workbook.add_format({"bold": True, "font_size": 14, "align": "center"})
        fmt_header = workbook.add_format({"bold": True, "border": 1, "align": "center", "valign": "vcenter"})
        fmt_cell = workbook.add_format({"border": 1, "align": "center", "valign": "vcenter"})
        fmt_num = workbook.add_format({"border": 1, "align": "center", "valign": "vcenter", "num_format": "0.00"})
        fmt_tot = workbook.add_format({"bold": True, "border": 1, "align": "center", "valign": "vcenter", "num_format": "0.00"})

        for move in moves:
            sheet = workbook.add_worksheet((move.name or "Packing Dates")[:31])

            base._set_columns(sheet, show_dates=True)

            sheet.merge_range(0, 0, 0, 14, "Packing List (With Dates)", fmt_title)

            sheet.write(2, 0, "Company", fmt_header)
            sheet.write(2, 1, move.company_id.name or "", fmt_cell)
            sheet.write(3, 0, "Invoice No", fmt_header)
            sheet.write(3, 1, move.name or "", fmt_cell)
            sheet.write(4, 0, "Date", fmt_header)
            sheet.write(4, 1, str(move.invoice_date or ""), fmt_cell)

            sheet.write(2, 11, "Customer", fmt_header)
            sheet.write(2, 12, move.partner_id.name or "", fmt_cell)
            sheet.write(3, 11, "Email", fmt_header)
            sheet.write(3, 12, move.partner_id.email or "", fmt_cell)

            start_row = 6
            col_count = base._write_header(sheet, start_row, 0, show_dates=True, fmt_header=fmt_header)

            row = start_row + 1
            res = computed.get(move.id, {})
            lines = res.get("lines", [])
            totals = res.get("totals", {})

            for l in lines:
                c = 0
                sheet.write(row, c, l.get("barcode", ""), fmt_cell); c += 1
                sheet.write(row, c, l.get("hs_code", ""), fmt_cell); c += 1

                sheet.write(row, c, str(l.get("production_date") or ""), fmt_cell); c += 1
                sheet.write(row, c, str(l.get("expiry_date") or ""), fmt_cell); c += 1

                sheet.write(row, c, l.get("product_name", ""), fmt_cell); c += 1
                sheet.write_number(row, c, float(l.get("net_w", 0.0)), fmt_num); c += 1
                sheet.write_number(row, c, float(l.get("gross_w", 0.0)), fmt_num); c += 1
                sheet.write(row, c, l.get("package_type", ""), fmt_cell); c += 1
                sheet.write_number(row, c, float(l.get("units", 0.0)), fmt_num); c += 1
                sheet.write_number(row, c, float(l.get("qty_per_carton", 0) or 0), fmt_num); c += 1
                sheet.write_number(row, c, float(l.get("cartons", 0.0)), fmt_num); c += 1
                sheet.write_number(row, c, float(l.get("net_total", 0.0)), fmt_num); c += 1
                sheet.write_number(row, c, float(l.get("gross_total", 0.0)), fmt_num); c += 1
                row += 1

            # Totals row (same concept)
            sheet.merge_range(row, 0, row, 7, "Totals", fmt_header)
            sheet.write_number(row, 8, float(totals.get("tot_units", 0.0)), fmt_tot)
            sheet.write(row, 9, "", fmt_header)
            sheet.write_number(row, 10, float(totals.get("tot_cartons", 0.0)), fmt_tot)
            sheet.write_number(row, 11, float(totals.get("tot_net", 0.0)), fmt_tot)
            sheet.write_number(row, 12, float(totals.get("tot_gross", 0.0)), fmt_tot)
