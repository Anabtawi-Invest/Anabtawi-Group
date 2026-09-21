# -*- coding: utf-8 -*-
import base64
import io
from collections import defaultdict
from datetime import datetime, time

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_is_zero


class StockPeriodMovementWizard(models.TransientModel):
    _name = "stock.period.movement.wizard"
    _description = "Stock Period Movement Report Wizard"

    date_from = fields.Datetime(
        string="From Date",
        required=True,
        default=lambda self: datetime.combine(
            fields.Date.context_today(self).replace(day=1), time.min
        ),
    )
    date_to = fields.Datetime(
        string="To Date",
        required=True,
        default=lambda self: datetime.combine(fields.Date.context_today(self), time.max),
    )
    all_locations = fields.Boolean(
        string="All Warehouse Stock Locations",
        default=True,
    )
    location_ids = fields.Many2many(
        "stock.location",
        "stock_period_movement_wiz_location_rel",
        "wizard_id",
        "location_id",
        string="Locations",
        domain="[('usage', '=', 'internal')]",
    )
    include_child_locations = fields.Boolean(
        string="Include Child Locations",
        default=True,
    )
    all_products = fields.Boolean(
        string="All Products",
        default=True,
    )
    product_ids = fields.Many2many(
        "product.product",
        "stock_period_movement_wiz_product_rel",
        "wizard_id",
        "product_id",
        string="Products",
        domain="[('is_storable', '=', True)]",
    )
    hide_zero_lines = fields.Boolean(
        string="Hide Zero Lines",
        default=True,
        help="Hide rows where opening, movements and closing are all zero.",
    )
    line_ids = fields.One2many(
        "stock.period.movement.report.line",
        "wizard_id",
        string="Report Lines",
        readonly=True,
    )

    @api.onchange("all_locations")
    def _onchange_all_locations(self):
        if self.all_locations:
            self.location_ids = [(5, 0, 0)]

    @api.onchange("all_products")
    def _onchange_all_products(self):
        if self.all_products:
            self.product_ids = [(5, 0, 0)]

    def _get_report_locations(self):
        self.ensure_one()
        if self.all_locations:
            warehouses = self.env["stock.warehouse"].search([
                ("company_id", "in", self.env.companies.ids),
            ])
            locations = warehouses.mapped("lot_stock_id")
            if not locations:
                raise UserError(_("No warehouse stock locations were found."))
            return locations
        if not self.location_ids:
            raise UserError(_("Please select at least one location or enable All Warehouse Stock Locations."))
        return self.location_ids

    def _get_expanded_location_ids(self, locations):
        self.ensure_one()
        if self.include_child_locations:
            return self.env["stock.location"].search([("id", "child_of", locations.ids)]).ids
        return locations.ids

    def _get_current_qty_by_product(self, location_ids, product_ids):
        return {
            product.id: quantity
            for product, quantity in self.env["stock.quant"]._read_group(
                [
                    ("location_id", "in", location_ids),
                    ("product_id", "in", product_ids),
                ],
                ["product_id"],
                ["quantity:sum"],
            )
        }

    def _get_done_move_qty(self, location_ids, product_ids, date_domain, incoming=True):
        """Sum done move-line qty with an extra date domain."""
        domain = [
            ("state", "=", "done"),
            ("product_id", "in", product_ids),
            ("company_id", "in", self.env.companies.ids),
        ] + date_domain
        if incoming:
            domain += [
                ("location_dest_id", "in", location_ids),
                ("location_id", "not in", location_ids),
            ]
        else:
            domain += [
                ("location_id", "in", location_ids),
                ("location_dest_id", "not in", location_ids),
            ]
        return {
            product.id: qty
            for product, qty in self.env["stock.move.line"]._read_group(
                domain,
                ["product_id"],
                ["quantity_product_uom:sum"],
            )
        }

    def _qty_opening(self, location_ids, product_ids):
        """Stock at the beginning of the period (before date_from)."""
        current = self._get_current_qty_by_product(location_ids, product_ids)
        date_domain = [("date", ">=", self.date_from)]
        in_after = self._get_done_move_qty(location_ids, product_ids, date_domain, incoming=True)
        out_after = self._get_done_move_qty(location_ids, product_ids, date_domain, incoming=False)
        return {
            product_id: (
                current.get(product_id, 0.0)
                - in_after.get(product_id, 0.0)
                + out_after.get(product_id, 0.0)
            )
            for product_id in product_ids
        }

    def _qty_closing(self, location_ids, product_ids):
        """Stock at the end of the period (through date_to)."""
        current = self._get_current_qty_by_product(location_ids, product_ids)
        date_domain = [("date", ">", self.date_to)]
        in_after = self._get_done_move_qty(location_ids, product_ids, date_domain, incoming=True)
        out_after = self._get_done_move_qty(location_ids, product_ids, date_domain, incoming=False)
        return {
            product_id: (
                current.get(product_id, 0.0)
                - in_after.get(product_id, 0.0)
                + out_after.get(product_id, 0.0)
            )
            for product_id in product_ids
        }

    def _classify_move_line(self, move_line, location_ids):
        """Return ('in'|'out', bucket) or (False, False) if ignored (internal within scope)."""
        src_id = move_line.location_id.id
        dest_id = move_line.location_dest_id.id
        src_in = src_id in location_ids
        dest_in = dest_id in location_ids
        if src_in and dest_in:
            return False, False
        if dest_in and not src_in:
            direction = "in"
        elif src_in and not dest_in:
            direction = "out"
        else:
            return False, False

        move = move_line.move_id
        code = (
            move.picking_type_id.code
            or move.picking_id.picking_type_id.code
            or False
        )
        src_usage = move_line.location_id.usage
        dest_usage = move_line.location_dest_id.usage

        if direction == "in":
            if code == "incoming" or src_usage == "supplier":
                return "in", "receipt"
            if code == "internal":
                return "in", "transfer_in"
            if code == "outgoing":
                # unusual return path; treat as sale reversal / other
                return "in", "other_in"
            if src_usage in ("inventory", "production", "transit"):
                if src_usage == "transit" or code == "internal":
                    return "in", "transfer_in"
                return "in", "other_in"
            return "in", "other_in"

        # direction == out
        if code == "outgoing" or dest_usage == "customer":
            return "out", "sale"
        if code == "internal":
            return "out", "transfer_out"
        if code == "incoming":
            return "out", "other_out"
        if dest_usage in ("inventory", "production", "transit"):
            if dest_usage == "transit" or code == "internal":
                return "out", "transfer_out"
            return "out", "other_out"
        return "out", "other_out"

    def _get_period_movements(self, location_ids, product_ids):
        MoveLine = self.env["stock.move.line"]
        lines = MoveLine.search([
            ("state", "=", "done"),
            ("product_id", "in", product_ids),
            ("company_id", "in", self.env.companies.ids),
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
            "|",
            ("location_id", "in", location_ids),
            ("location_dest_id", "in", location_ids),
        ])
        # Prefetch related fields used in classification
        lines.mapped("move_id.picking_type_id")
        lines.mapped("location_id.usage")
        lines.mapped("location_dest_id.usage")

        empty = lambda: {
            "receipt": 0.0,
            "sale": 0.0,
            "transfer_in": 0.0,
            "transfer_out": 0.0,
            "other_in": 0.0,
            "other_out": 0.0,
        }
        data = defaultdict(empty)
        location_id_set = set(location_ids)

        for move_line in lines:
            direction, bucket = self._classify_move_line(move_line, location_id_set)
            if not bucket:
                continue
            qty = move_line.quantity_product_uom
            data[move_line.product_id.id][bucket] += qty
        return data

    def _get_products_for_locations(self, locations):
        self.ensure_one()
        Product = self.env["product.product"]
        if not self.all_products:
            if not self.product_ids:
                raise UserError(_("Please select at least one product or enable All Products."))
            return self.product_ids.filtered(lambda p: p.is_storable)

        location_ids = self._get_expanded_location_ids(locations)
        product_ids = set()

        for product, __count in self.env["stock.quant"]._read_group(
            [
                ("location_id", "in", location_ids),
                ("quantity", "!=", 0),
                ("product_id.is_storable", "=", True),
            ],
            ["product_id"],
            ["__count"],
        ):
            if product:
                product_ids.add(product.id)

        MoveLine = self.env["stock.move.line"]
        ml_domain = [
            ("state", "=", "done"),
            ("product_id.is_storable", "=", True),
            ("company_id", "in", self.env.companies.ids),
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
            "|",
            ("location_id", "in", location_ids),
            ("location_dest_id", "in", location_ids),
        ]
        for product, __count in MoveLine._read_group(ml_domain, ["product_id"], ["__count"]):
            if product:
                product_ids.add(product.id)

        # Also include products with stock at opening/closing even if no period moves
        # (already covered by quant search above for current; opening may differ —
        # products that only had stock at opening are found via moves after date_from)
        after_opening_domain = [
            ("state", "=", "done"),
            ("product_id.is_storable", "=", True),
            ("company_id", "in", self.env.companies.ids),
            ("date", ">", self.date_from),
            "|",
            ("location_id", "in", location_ids),
            ("location_dest_id", "in", location_ids),
        ]
        for product, __count in MoveLine._read_group(
            after_opening_domain, ["product_id"], ["__count"]
        ):
            if product:
                product_ids.add(product.id)

        return Product.browse(list(product_ids))

    def _build_report_values(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_("From Date must be before To Date."))

        locations = self._get_report_locations()
        products = self._get_products_for_locations(locations)
        if not products:
            return []

        vals_list = []
        for location in locations:
            location_ids = self._get_expanded_location_ids(location)
            opening_map = self._qty_opening(location_ids, products.ids)
            closing_map = self._qty_closing(location_ids, products.ids)
            movements = self._get_period_movements(location_ids, products.ids)

            for product in products:
                opening = opening_map.get(product.id, 0.0)
                closing = closing_map.get(product.id, 0.0)
                move = movements.get(product.id) or {}
                receipt = move.get("receipt", 0.0)
                sale = move.get("sale", 0.0)
                transfer_in = move.get("transfer_in", 0.0)
                transfer_out = move.get("transfer_out", 0.0)
                other_in = move.get("other_in", 0.0)
                other_out = move.get("other_out", 0.0)

                if self.hide_zero_lines and all(
                    float_is_zero(v, precision_rounding=product.uom_id.rounding)
                    for v in (
                        opening, receipt, sale, transfer_in, transfer_out,
                        other_in, other_out, closing,
                    )
                ):
                    continue

                vals_list.append({
                    "location_id": location.id,
                    "product_id": product.id,
                    "qty_opening": opening,
                    "qty_receipt": receipt,
                    "qty_sale": sale,
                    "qty_transfer_in": transfer_in,
                    "qty_transfer_out": transfer_out,
                    "qty_other_in": other_in,
                    "qty_other_out": other_out,
                    "qty_closing": closing,
                })
        return vals_list

    def action_generate_report(self):
        self.ensure_one()
        self.line_ids.unlink()
        vals_list = self._build_report_values()
        if not vals_list:
            raise UserError(_("No data found for the selected filters."))
        self.write({"line_ids": [(0, 0, vals) for vals in vals_list]})
        return {
            "name": _("Stock Period Movement Report"),
            "type": "ir.actions.act_window",
            "res_model": "stock.period.movement.report.line",
            "view_mode": "list,pivot",
            "domain": [("wizard_id", "=", self.id)],
            "context": {"search_default_group_by_location": 1},
        }

    def _generate_xlsx_content(self):
        self.ensure_one()
        import xlsxwriter  # pylint: disable=import-outside-toplevel

        if not self.line_ids:
            vals_list = self._build_report_values()
            if not vals_list:
                raise UserError(_("No data found for the selected filters."))
            self.write({"line_ids": [(0, 0, vals) for vals in vals_list]})

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet(_("Period Movement"))
        sheet.right_to_left()

        header_style = workbook.add_format({
            "bold": True,
            "bg_color": "#D9E1F2",
            "border": 1,
            "align": "center",
        })
        text_style = workbook.add_format({"border": 1})
        number_style = workbook.add_format({"border": 1, "num_format": "#,##0.00"})

        headers = [
            _("Location"),
            _("Internal Reference"),
            _("Product"),
            _("Unit of Measure"),
            _("Opening"),
            _("Receipt"),
            _("Sale"),
            _("Transfer In"),
            _("Transfer Out"),
            _("Other In"),
            _("Other Out"),
            _("Closing"),
        ]
        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_style)

        sheet.set_column(0, 0, 35)
        sheet.set_column(1, 1, 18)
        sheet.set_column(2, 2, 45)
        sheet.set_column(3, 3, 16)
        sheet.set_column(4, 11, 14)

        row = 1
        for line in self.line_ids.sorted(
            key=lambda rec: (rec.location_id.complete_name or "", rec.product_id.display_name or "")
        ):
            sheet.write(row, 0, line.location_name or line.location_id.display_name, text_style)
            sheet.write(row, 1, line.default_code or "", text_style)
            sheet.write(row, 2, line.product_id.display_name, text_style)
            sheet.write(row, 3, line.uom_name or "", text_style)
            sheet.write_number(row, 4, line.qty_opening, number_style)
            sheet.write_number(row, 5, line.qty_receipt, number_style)
            sheet.write_number(row, 6, line.qty_sale, number_style)
            sheet.write_number(row, 7, line.qty_transfer_in, number_style)
            sheet.write_number(row, 8, line.qty_transfer_out, number_style)
            sheet.write_number(row, 9, line.qty_other_in, number_style)
            sheet.write_number(row, 10, line.qty_other_out, number_style)
            sheet.write_number(row, 11, line.qty_closing, number_style)
            row += 1

        workbook.close()
        return output.getvalue()

    def action_export_excel(self):
        self.ensure_one()
        content = self._generate_xlsx_content()
        filename = "stock_period_movement_report.xlsx"
        attachment = self.env["ir.attachment"].create({
            "name": filename,
            "type": "binary",
            "datas": base64.b64encode(content),
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "res_model": self._name,
            "res_id": self.id,
        })
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }
