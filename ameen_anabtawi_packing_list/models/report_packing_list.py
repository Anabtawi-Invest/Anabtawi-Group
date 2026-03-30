# models/report_packing_list.py
from odoo import models

class ReportPackingList(models.AbstractModel):
    _name = "report.softobia_packing_list.packing_list_template"
    _description = "Packing List Report"

    def _get_hs_code(self, product_tmpl):
        # آمن: إذا الحقل غير موجود لا نكسر التقرير
        if "hs_code" in product_tmpl._fields:
            return product_tmpl.hs_code or ""
        # بعض قواعد البيانات قد تستخدم commodity_code أو intrastat_code_id حسب التوطين/الموديول
        if "commodity_code" in product_tmpl._fields:
            return product_tmpl.commodity_code or ""
        return ""

    def _get_terms_from_so(self, move):
        # جمع شروط البيع من أوامر البيع المرتبطة بسطور الفاتورة
        sale_orders = move.invoice_line_ids.mapped("sale_line_ids.order_id")
        notes = [n for n in sale_orders.mapped("note") if n]
        # إزالة التكرار مع الحفاظ على الترتيب
        unique = []
        for n in notes:
            if n not in unique:
                unique.append(n)
        return "\n\n".join(unique)

    def _get_report_values(self, docids, data=None):
        docs = self.env["account.move"].browse(docids)
        result_docs = []
        for move in docs:
            lines = []
            tot_units = tot_net = tot_gross = tot_cartons = 0.0

            for line in move.invoice_line_ids:
                if line.display_type or not line.product_id:
                    continue

                tmpl = line.product_id.product_tmpl_id
                units = float(line.quantity or 0.0)

                net_w = float(tmpl.x_net_weight_kg or 0.0)
                gross_w = float(tmpl.x_gross_weight_kg or 0.0)

                # qty/carton: نأخذه من sale line إن وجد، وإلا من المنتج
                qty_per_carton = 0
                if line.sale_line_ids:
                    qty_per_carton = int(line.sale_line_ids[0].x_qty_per_carton or 0)
                if not qty_per_carton:
                    qty_per_carton = int(tmpl.x_qty_per_carton or 0)

                cartons = (units / qty_per_carton) if qty_per_carton else 0.0

                net_total = units * net_w
                gross_total = units * gross_w

                hs_code = self._get_hs_code(tmpl)

                lines.append({
                    "product_name": line.product_id.display_name,
                    "barcode": line.product_id.barcode or "",
                    "hs_code": hs_code,
                    "package_type": tmpl.x_package_type_id.name if tmpl.x_package_type_id else "",
                    "qty_per_carton": qty_per_carton,
                    "units": units,
                    "cartons": cartons,
                    "net_w": net_w,
                    "gross_w": gross_w,
                    "net_total": net_total,
                    "gross_total": gross_total,
                })

                tot_units += units
                tot_net += net_total
                tot_gross += gross_total
                tot_cartons += cartons

            result_docs.append({
                "move": move,
                "lines": lines,
                "tot_units": tot_units,
                "tot_net": tot_net,
                "tot_gross": tot_gross,
                "tot_cartons": tot_cartons,
                "terms": self._get_terms_from_so(move),
            })

        return {"docs": result_docs}
