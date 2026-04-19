from odoo import models


class ReportPackingListBase(models.AbstractModel):
    _name = "report.ameen_anabtawi_packing_list.pl_base"
    _description = "Packing List Base Logic"

    def _get_hs_code(self, product_tmpl):
        if "hs_code" in product_tmpl._fields:
            return product_tmpl.hs_code or ""
        if "commodity_code" in product_tmpl._fields:
            return product_tmpl.commodity_code or ""
        return ""

    def _get_sale_orders_from_move(self, move):
        sos = move.invoice_line_ids.mapped("sale_line_ids.order_id")
        if sos:
            return sos
        if move.invoice_origin:
            so = self.env["sale.order"].search([("name", "=", move.invoice_origin)], limit=1)
            if so:
                return so
        return self.env["sale.order"]

    def _get_done_pickings_from_move(self, move):
        sale_orders = self._get_sale_orders_from_move(move)
        if not sale_orders:
            return self.env["stock.picking"]
        return sale_orders.mapped("picking_ids").filtered(lambda p: p.state == "done")

    def _find_so_line_for_product(self, move, product):
        so_lines = move.invoice_line_ids.mapped("sale_line_ids").filtered(lambda sl: sl.product_id.id == product.id)
        return so_lines[:1] if so_lines else self.env["sale.order.line"]

    def _get_qty_per_carton(self, move, product):
        sl = self._find_so_line_for_product(move, product)
        if sl and sl.x_qty_per_carton:
            return int(sl.x_qty_per_carton)
        return int(product.product_tmpl_id.x_qty_per_carton or 0)

    def _get_dates(self, move, product):
        sl = self._find_so_line_for_product(move, product)
        if sl:
            return sl.x_production_date or False, sl.x_expiry_date or False
        return False, False

    def _compute_from_pickings(self, move):
        pickings = self._get_done_pickings_from_move(move)
        if not pickings:
            return None

        mlines = pickings.mapped("move_line_ids").filtered(lambda ml: ml.product_id and ml.qty_done)

        product_qty = {}
        if mlines:
            for ml in mlines:
                product_qty[ml.product_id] = product_qty.get(ml.product_id, 0.0) + float(ml.qty_done or 0.0)
        else:
            moves = pickings.mapped("move_ids").filtered(lambda m: m.product_id)
            for mv in moves:
                qty = float(mv.quantity_done or 0.0)
                if qty == 0.0:
                    qty = float(mv.product_uom_qty or 0.0)
                if qty:
                    product_qty[mv.product_id] = product_qty.get(mv.product_id, 0.0) + qty

        lines = []
        tot_units = tot_net = tot_gross = tot_cartons = 0.0

        for product, units in product_qty.items():
            tmpl = product.product_tmpl_id
            units = float(units or 0.0)

            net_w = float(tmpl.x_net_weight_kg or 0.0)
            gross_w = float(tmpl.x_gross_weight_kg or 0.0)

            qty_per_carton = self._get_qty_per_carton(move, product)
            cartons = (units / qty_per_carton) if qty_per_carton else 0.0

            net_total = units * net_w
            gross_total = units * gross_w

            prod_date, exp_date = self._get_dates(move, product)

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

            qty_per_carton = 0
            if inv_line.sale_line_ids and inv_line.sale_line_ids[0].x_qty_per_carton:
                qty_per_carton = int(inv_line.sale_line_ids[0].x_qty_per_carton)
            if not qty_per_carton:
                qty_per_carton = int(tmpl.x_qty_per_carton or 0)

            cartons = (units / qty_per_carton) if qty_per_carton else 0.0

            net_total = units * net_w
            gross_total = units * gross_w

            prod_date = exp_date = False
            if inv_line.sale_line_ids:
                prod_date = inv_line.sale_line_ids[0].x_production_date or False
                exp_date = inv_line.sale_line_ids[0].x_expiry_date or False

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
        base = self.env["report.ameen_anabtawi_packing_list.pl_base"]

        lines_map, totals_map = {}, {}
        for move in docs:
            res = base._compute_from_pickings(move)
            if res is None:
                res = base._compute_from_invoice(move)

            lines_map[move.id] = res["lines"]
            totals_map[move.id] = res["totals"]

        return {
            "doc_ids": docs.ids,
            "doc_model": "account.move",
            "docs": docs,
            "lines_map": lines_map,
            "totals_map": totals_map,
            "show_dates": False,
        }


class ReportPackingListWithDates(models.AbstractModel):
    _name = "report.ameen_anabtawi_packing_list.pl_date_tmpl"
    _description = "Packing List (With Dates)"

    def _get_report_values(self, docids, data=None):
        docs = self.env["account.move"].browse(docids)
        base = self.env["report.ameen_anabtawi_packing_list.pl_base"]

        lines_map, totals_map = {}, {}
        for move in docs:
            res = base._compute_from_pickings(move)
            if res is None:
                res = base._compute_from_invoice(move)

            lines_map[move.id] = res["lines"]
            totals_map[move.id] = res["totals"]

        return {
            "doc_ids": docs.ids,
            "doc_model": "account.move",
            "docs": docs,
            "lines_map": lines_map,
            "totals_map": totals_map,
            "show_dates": True,
        }
