from odoo import models


class ReportPackingList(models.AbstractModel):
    _name = "report.ameen_anabtawi_packing_list.packing_list_template"
    _description = "Packing List Report"

    # -------------------------
    # Helpers
    # -------------------------
    def _get_hs_code(self, product_tmpl):
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

    def _get_sale_orders_from_move(self, move):
        # Invoices created from SO will have sale_line_ids link
        return move.invoice_line_ids.mapped("sale_line_ids.order_id")

    def _get_pickings_from_move(self, move):
        """
        Best-effort to get related deliveries:
        - from SO pickings if invoice comes from SO
        - else try by invoice_origin matching SO name (common)
        """
        sale_orders = self._get_sale_orders_from_move(move)
        if sale_orders:
            return sale_orders.mapped("picking_ids")

        # fallback: try origin -> sale order
        if move.invoice_origin:
            so = self.env["sale.order"].search([("name", "=", move.invoice_origin)], limit=1)
            if so:
                return so.picking_ids

        return self.env["stock.picking"]

    # -------------------------
    # Compute lines from Picking
    # -------------------------
    def _compute_lines_from_pickings(self, move):
        pickings = self._get_pickings_from_move(move).filtered(lambda p: p.state == "done")
        if not pickings:
            return None  # signal: no picking lines

        lines = []
        tot_units = tot_net = tot_gross = tot_cartons = 0.0

        # Prefer move_line_ids (qty_done per lot/package), else moves
        move_lines = pickings.mapped("move_line_ids").filtered(lambda ml: ml.product_id and ml.qty_done)

        if move_lines:
            # group by product to have one line per product
            grouped = {}
            for ml in move_lines:
                key = ml.product_id.id
                grouped.setdefault(key, {"product": ml.product_id, "qty": 0.0})
                grouped[key]["qty"] += float(ml.qty_done or 0.0)

            items = grouped.values()
        else:
            moves = pickings.mapped("move_ids").filtered(lambda m: m.product_id and (m.quantity_done or m.product_uom_qty))
            items = []
            for m in moves:
                qty = float(m.quantity_done or 0.0)
                if qty == 0.0:
                    qty = float(m.product_uom_qty or 0.0)
                items.append({"product": m.product_id, "qty": qty})

        for it in items:
            product = it["product"]
            units = float(it["qty"] or 0.0)

            tmpl = product.product_tmpl_id
            net_w = float(tmpl.x_net_weight_kg or 0.0)
            gross_w = float(tmpl.x_gross_weight_kg or 0.0)

            # qty/carton from sale line if exists
            qty_per_carton = 0
            # try find a sale line by product (best-effort)
            so_lines = move.invoice_line_ids.mapped("sale_line_ids").filtered(lambda sl: sl.product_id.id == product.id)
            if so_lines:
                qty_per_carton = int(so_lines[0].x_qty_per_carton or 0)
            if not qty_per_carton:
                qty_per_carton = int(tmpl.x_qty_per_carton or 0)

            cartons = (units / qty_per_carton) if qty_per_carton else 0.0

            net_total = units * net_w
            gross_total = units * gross_w

            lines.append({
                "product_name": product.display_name,
                "barcode": product.barcode or "",
                "hs_code": self._get_hs_code(tmpl),
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

    # -------------------------
    # Fallback: invoice lines (as before)
    # -------------------------
    def _compute_lines_from_invoice(self, move):
        lines = []
        tot_units = tot_net = tot_gross = tot_cartons = 0.0

        for line in move.invoice_line_ids:
            if line.display_type or not line.product_id:
                continue

            tmpl = line.product_id.product_tmpl_id
            units = float(line.quantity or 0.0)

            net_w = float(tmpl.x_net_weight_kg or 0.0)
            gross_w = float(tmpl.x_gross_weight_kg or 0.0)

            qty_per_carton = 0
            if line.sale_line_ids:
                qty_per_carton = int(line.sale_line_ids[0].x_qty_per_carton or 0)
            if not qty_per_carton:
                qty_per_carton = int(tmpl.x_qty_per_carton or 0)

            cartons = (units / qty_per_carton) if qty_per_carton else 0.0

            net_total = units * net_w
            gross_total = units * gross_w

            lines.append({
                "product_name": line.product_id.display_name,
                "barcode": line.product_id.barcode or "",
                "hs_code": self._get_hs_code(tmpl),
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

    # -------------------------
    # Report values
    # -------------------------
    def _get_report_values(self, docids, data=None):
        docs = self.env["account.move"].browse(docids)

        lines_map = {}
        totals_map = {}
        terms_map = {}

        for move in docs:
            # Try from pickings first
            res = self._compute_lines_from_pickings(move)
            if res is None:
                res = self._compute_lines_from_invoice(move)

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
