from odoo import models


class ReportPackingListBase(models.AbstractModel):
    _name = "report.ameen_anabtawi_packing_list.packing_list_base"
    _description = "Packing List Report Base (Shared Logic)"

    def _get_hs_code(self, product_tmpl):
        if "hs_code" in product_tmpl._fields:
            return product_tmpl.hs_code or ""
        if "commodity_code" in product_tmpl._fields:
            return product_tmpl.commodity_code or ""
        return ""

    def _get_qty_per_carton_from_invoice_line(self, inv_line):
        # prefer SO line value
        if inv_line.sale_line_ids:
            v = int(inv_line.sale_line_ids[0].x_qty_per_carton or 0)
            if v:
                return v
        # fallback product
        return int(inv_line.product_id.product_tmpl_id.x_qty_per_carton or 0)

    def _get_dates_from_invoice_line(self, inv_line):
        # from SO line if exists
        prod = exp = False
        if inv_line.sale_line_ids:
            sl = inv_line.sale_line_ids[0]
            prod = sl.x_production_date
            exp = sl.x_expiry_date
        return prod, exp

    def _compute_from_invoice(self, move):
        lines = []
        tot_units = tot_net = tot_gross = tot_cartons = 0.0

        for inv_line in move.invoice_line_ids:
            if inv_line.display_type or not inv_line.product_id:
                continue

            product = inv_line.product_id
            tmpl = product.product_tmpl_id

            units = float(inv_line.quantity or 0.0)
            net_w = float(tmpl.x_net_weight_kg or 0.0)
            gross_w = float(tmpl.x_gross_weight_kg or 0.0)

            qty_per_carton = self._get_qty_per_carton_from_invoice_line(inv_line)
            cartons = (units / qty_per_carton) if qty_per_carton else 0.0

            net_total = units * net_w
            gross_total = units * gross_w

            prod_date, exp_date = self._get_dates_from_invoice_line(inv_line)

            lines.append({
                "barcode": product.barcode or "",
                "hs_code": self._get_hs_code(tmpl),
                "production_date": prod_date,
                "expiry_date": exp_date,
                "product_name": product.display_name,
                "net_w": net_w,
                "gross_w": gross_w,
                "package_type": tmpl.x_package_type_id.name if tmpl.x_package_type_id else "",
                "units": units,
                "qty_per_carton": qty_per_carton,
                "cartons": cartons,
                "net_total": net_total,
                "gross_total": gross_total,
            })

            tot_units += units
            tot_net += net_total
            tot_gross += gross_total
            tot_cartons += cartons

        return {
            "lines": lines,
            "totals": {
                "tot_units": tot_units,
                "tot_net": tot_net,
                "tot_gross": tot_gross,
                "tot_cartons": tot_cartons,
            }
        }


class ReportPackingListNoDates(models.AbstractModel):
    _name = "report.ameen_anabtawi_packing_list.packing_list_template"
    _description = "Packing List (No Dates)"

    def _get_report_values(self, docids, data=None):
        docs = self.env["account.move"].browse(docids)
        base = self.env["report.ameen_anabtawi_packing_list.packing_list_base"]

        lines_map, totals_map = {}, {}
        for move in docs:
            res = base._compute_from_invoice(move)
            lines_map[move.id] = res["lines"]
            totals_map[move.id] = res["totals"]

        return {
            "doc_ids": docs.ids,
            "doc_model": "account.move",
            "docs": docs,
            "lines_map": lines_map,
            "totals_map": totals_map,
            "show_dates": False,  # IMPORTANT
        }


class ReportPackingListWithDates(models.AbstractModel):
    _name = "report.ameen_anabtawi_packing_list.packing_list_template_with_dates"
    _description = "Packing List (With Dates)"

    def _get_report_values(self, docids, data=None):
        docs = self.env["account.move"].browse(docids)
        base = self.env["report.ameen_anabtawi_packing_list.packing_list_base"]

        lines_map, totals_map = {}, {}
        for move in docs:
            res = base._compute_from_invoice(move)
            lines_map[move.id] = res["lines"]
            totals_map[move.id] = res["totals"]

        return {
            "doc_ids": docs.ids,
            "doc_model": "account.move",
            "docs": docs,
            "lines_map": lines_map,
            "totals_map": totals_map,
            "show_dates": True,  # IMPORTANT
        }
