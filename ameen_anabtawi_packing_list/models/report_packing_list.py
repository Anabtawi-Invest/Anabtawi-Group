from odoo import models

class ReportPackingList(models.AbstractModel):
    _name = "report.ameen_anabtawi_packing_list.packing_list_template"
    _description = "Packing List Report"

    def _get_hs_code(self, product_tmpl):
        # Safe read: field may not exist depending on modules/localization
        if "hs_code" in product_tmpl._fields:
            return product_tmpl.hs_code or ""
        if "commodity_code" in product_tmpl._fields:
            return product_tmpl.commodity_code or ""
        return ""

    def _get_terms_from_so(self, move):
        sale_orders = move.invoice_line_ids.mapped("sale_line_ids.order_id")
        notes = [n for n in sale_orders.mapped("note") if n]
        unique = []
        for n in notes:
            if n not in unique:
                unique.append(n)
        return "\n\n".join(unique)

    def _compute_for_move(self, move):
        lines = []
        tot_units = tot_net = tot_gross = tot_cartons = 0.0

        for line in move.invoice_line_ids:
            if line.display_type or not line.product_id:
                continue

            tmpl = line.product_id.product_tmpl_id
            units = float(line.quantity or 0.0)

            net_w = float(tmpl.x_net_weight_kg or 0.0)
            gross_w = float(tmpl.x_gross_weight_kg or 0.0)

            # qty/carton: from sale line if exists else from product
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

        return {
            "lines": lines,
            "tot_units": tot_units,
            "tot_net": tot_net,
            "tot_gross": tot_gross,
            "tot_cartons": tot_cartons,
            "terms": self._get_terms_from_so(move),
        }

    def _get_report_values(self, docids, data=None):
        docs = self.env["account.move"].browse(docids)

        lines_map = {}
        totals_map = {}
        terms_map = {}

        for move in docs:
            res = self._compute_for_move(move)
            lines_map[move.id] = res["lines"]
            totals_map[move.id] = {
                "tot_units": res["tot_units"],
                "tot_net": res["tot_net"],
                "tot_gross": res["tot_gross"],
                "tot_cartons": res["tot_cartons"],
            }
            terms_map[move.id] = res["terms"]

        return {
            "doc_ids": docs.ids,
            "doc_model": "account.move",
            "docs": docs,
            "lines_map": lines_map,
            "totals_map": totals_map,
            "terms_map": terms_map,
        }
