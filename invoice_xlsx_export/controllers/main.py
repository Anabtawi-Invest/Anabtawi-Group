import io
import xlsxwriter

from odoo import http
from odoo.http import request, content_disposition

class InvoiceXlsxExportController(http.Controller):

    @http.route("/invoice_xlsx_export/<int:move_id>", type="http", auth="user")
    def invoice_xlsx(self, move_id, lang="en_US", **kwargs):
        move = request.env["account.move"].browse(move_id)
        move.check_access_rights("read")
        move.check_access_rule("read")

        # لغة التقرير (للعناوين فقط)
        is_ar = (lang or "").startswith("ar")

        out = io.BytesIO()
        wb = xlsxwriter.Workbook(out, {"in_memory": True})
        ws = wb.add_worksheet("Invoice")

        # Formats
        fmt_title = wb.add_format({"bold": True, "font_size": 14, "align": "right" if is_ar else "left"})
        fmt_label = wb.add_format({"bold": True, "align": "right" if is_ar else "left"})
        fmt_text  = wb.add_format({"align": "right" if is_ar else "left"})
        fmt_money = wb.add_format({"num_format": "#,##0.00", "align": "right" if is_ar else "left"})
        fmt_head  = wb.add_format({"bold": True, "border": 1, "align": "center"})
        fmt_cell  = wb.add_format({"border": 1, "align": "right" if is_ar else "left"})
        fmt_cell_num = wb.add_format({"border": 1, "num_format": "#,##0.00", "align": "right" if is_ar else "left"})

        # Column widths
        ws.set_column("A:A", 45)
        ws.set_column("B:B", 10)
        ws.set_column("C:C", 14)
        ws.set_column("D:D", 18)
        ws.set_column("E:E", 16)

        r = 0
        company = move.company_id
        partner = move.partner_id

        title = "فاتورة" if is_ar else "Invoice"
        ws.write(r, 0, f"{company.name} - {title}", fmt_title); r += 2

        # Header blocks
        ws.write(r, 0, "العميل" if is_ar else "Customer", fmt_label)
        ws.write(r, 1, partner.name or "", fmt_text)
        ws.write(r, 3, "رقم الفاتورة" if is_ar else "Invoice No.", fmt_label)
        ws.write(r, 4, move.name or "", fmt_text); r += 1

        ws.write(r, 0, "تاريخ الفاتورة" if is_ar else "Invoice Date", fmt_label)
        ws.write(r, 1, str(move.invoice_date or ""), fmt_text)
        ws.write(r, 3, "العملة" if is_ar else "Currency", fmt_label)
        ws.write(r, 4, move.currency_id.name or "", fmt_text); r += 1

        # FDA (مثال شرطك السابق): اطبع فقط إذا بلد العميل != الأردن
        if partner.country_id and partner.country_id.code != "JO":
            fda_val = company.x_studio_char_field_159_1jikaoani or ""
            if fda_val:
                ws.write(r, 0, "رقم FDA" if is_ar else "FDA No.", fmt_label)
                ws.write(r, 1, fda_val, fmt_text)
                r += 1

        r += 1

        # Table header
        headers = [
            ("الوصف" if is_ar else "Description"),
            ("الكمية" if is_ar else "Qty"),
            ("سعر الوحدة" if is_ar else "Unit Price"),
            ("الضرائب" if is_ar else "Taxes"),
            ("الإجمالي" if is_ar else "Subtotal"),
        ]
        for c, h in enumerate(headers):
            ws.write(r, c, h, fmt_head)
        r += 1

        # Lines
        lines = move.invoice_line_ids.filtered(lambda l: not l.display_type)
        for line in lines:
            taxes = ", ".join(t.name for t in line.tax_ids)
            ws.write(r, 0, line.name or "", fmt_cell)
            ws.write_number(r, 1, float(line.quantity or 0.0), fmt_cell_num)
            ws.write_number(r, 2, float(line.price_unit or 0.0), fmt_cell_num)
            ws.write(r, 3, taxes, fmt_cell)
            ws.write_number(r, 4, float(line.price_subtotal or 0.0), fmt_cell_num)
            r += 1

        r += 1

        # Totals
        ws.write(r, 3, "غير شامل الضريبة" if is_ar else "Untaxed", fmt_label)
        ws.write_number(r, 4, float(move.amount_untaxed or 0.0), fmt_money); r += 1

        ws.write(r, 3, "الضريبة" if is_ar else "Tax", fmt_label)
        ws.write_number(r, 4, float(move.amount_tax or 0.0), fmt_money); r += 1

        ws.write(r, 3, "الإجمالي" if is_ar else "Total", fmt_label)
        ws.write_number(r, 4, float(move.amount_total or 0.0), fmt_money); r += 1

        wb.close()
        out.seek(0)

        filename = f"{(move.name or 'invoice').replace('/', '_')}_{lang}.xlsx"
        headers = [
            ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("Content-Disposition", content_disposition(filename)),
        ]
        return request.make_response(out.getvalue(), headers)
