# -*- coding: utf-8 -*-
import base64
import io
from datetime import datetime, time

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_is_zero


PLANNED_MOVE_STATES = ("waiting", "confirmed", "assigned", "partially_available")


class StockLocationQtyWizard(models.TransientModel):
    _name = "stock.location.qty.wizard"
    _description = "Stock Location Quantity Report Wizard"

    qty_mode = fields.Selection(
        [
            ("planned", "Incoming / Outgoing = Planned (Not Done)"),
            ("done", "Incoming / Outgoing = Done"),
        ],
        string="Incoming / Outgoing",
        required=True,
        default="planned",
        help="Planned: future moves not yet validated.\n"
             "Done: validated moves (already reflected in On Hand). "
             "Use a date range to see movement activity.",
    )
    date_from = fields.Datetime(
        string="From Date",
        help="Only for Done mode. Leave empty to include all done moves.",
    )
    date_to = fields.Datetime(
        string="To Date",
        help="Only for Done mode. Leave empty to include all done moves.",
    )
    all_locations = fields.Boolean(
        string="All Warehouse Stock Locations",
        default=True,
        help="Use each warehouse stock location. Disable to pick specific locations.",
    )
    location_ids = fields.Many2many(
        "stock.location",
        "stock_location_qty_wiz_location_rel",
        "wizard_id",
        "location_id",
        string="Locations",
        domain="[('usage', '=', 'internal')]",
    )
    include_child_locations = fields.Boolean(
        string="Include Child Locations",
        default=True,
        help="Roll up quantities from sub-locations under each selected location.",
    )
    all_products = fields.Boolean(
        string="All Products",
        default=True,
        help="Include storable products with stock and/or matching moves.",
    )
    product_ids = fields.Many2many(
        "product.product",
        "stock_location_qty_wiz_product_rel",
        "wizard_id",
        "product_id",
        string="Products",
        domain="[('is_storable', '=', True)]",
    )
    hide_zero_lines = fields.Boolean(
        string="Hide Zero Lines",
        default=True,
        help="Hide rows where On Hand, Incoming and Outgoing are all zero.",
    )
    line_ids = fields.One2many(
        "stock.location.qty.report.line",
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

    @api.onchange("qty_mode")
    def _onchange_qty_mode(self):
        if self.qty_mode != "done":
            self.date_from = False
            self.date_to = False
        elif not self.date_from and not self.date_to:
            today = fields.Date.context_today(self)
            self.date_from = datetime.combine(today.replace(day=1), time.min)
            self.date_to = datetime.combine(today, time.max)

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

    def _done_date_domain(self):
        domain = []
        if self.date_from:
            domain.append(("date", ">=", self.date_from))
        if self.date_to:
            domain.append(("date", "<=", self.date_to))
        return domain

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

        if self.qty_mode == "planned":
            Move = self.env["stock.move"]
            move_domain_base = [
                ("state", "in", PLANNED_MOVE_STATES),
                ("product_id.is_storable", "=", True),
                ("company_id", "in", self.env.companies.ids),
            ]
            for product, __count in Move._read_group(
                move_domain_base + [("location_dest_id", "in", location_ids)],
                ["product_id"],
                ["__count"],
            ):
                if product:
                    product_ids.add(product.id)
            for product, __count in Move._read_group(
                move_domain_base + [("location_id", "in", location_ids)],
                ["product_id"],
                ["__count"],
            ):
                if product:
                    product_ids.add(product.id)
        else:
            MoveLine = self.env["stock.move.line"]
            ml_domain_base = [
                ("state", "=", "done"),
                ("product_id.is_storable", "=", True),
                ("company_id", "in", self.env.companies.ids),
            ] + self._done_date_domain()
            for product, __count in MoveLine._read_group(
                ml_domain_base + [("location_dest_id", "in", location_ids)],
                ["product_id"],
                ["__count"],
            ):
                if product:
                    product_ids.add(product.id)
            for product, __count in MoveLine._read_group(
                ml_domain_base + [("location_id", "in", location_ids)],
                ["product_id"],
                ["__count"],
            ):
                if product:
                    product_ids.add(product.id)

        return Product.browse(list(product_ids))

    def _get_on_hand_by_product(self, location_ids, products):
        return {
            product.id: quantity
            for product, quantity in self.env["stock.quant"]._read_group(
                [
                    ("location_id", "in", location_ids),
                    ("product_id", "in", products.ids),
                ],
                ["product_id"],
                ["quantity:sum"],
            )
        }

    def _get_planned_in_out_by_product(self, location_ids, products):
        Move = self.env["stock.move"]
        base = [
            ("state", "in", PLANNED_MOVE_STATES),
            ("product_id", "in", products.ids),
            ("company_id", "in", self.env.companies.ids),
        ]
        # Exclude internal moves that stay inside the same location tree
        incoming = {
            product.id: qty
            for product, qty in Move._read_group(
                base + [
                    ("location_dest_id", "in", location_ids),
                    ("location_id", "not in", location_ids),
                ],
                ["product_id"],
                ["product_qty:sum"],
            )
        }
        outgoing = {
            product.id: qty
            for product, qty in Move._read_group(
                base + [
                    ("location_id", "in", location_ids),
                    ("location_dest_id", "not in", location_ids),
                ],
                ["product_id"],
                ["product_qty:sum"],
            )
        }
        return incoming, outgoing

    def _get_done_in_out_by_product(self, location_ids, products):
        MoveLine = self.env["stock.move.line"]
        base = [
            ("state", "=", "done"),
            ("product_id", "in", products.ids),
            ("company_id", "in", self.env.companies.ids),
        ] + self._done_date_domain()
        incoming = {
            product.id: qty
            for product, qty in MoveLine._read_group(
                base + [
                    ("location_dest_id", "in", location_ids),
                    ("location_id", "not in", location_ids),
                ],
                ["product_id"],
                ["quantity_product_uom:sum"],
            )
        }
        outgoing = {
            product.id: qty
            for product, qty in MoveLine._read_group(
                base + [
                    ("location_id", "in", location_ids),
                    ("location_dest_id", "not in", location_ids),
                ],
                ["product_id"],
                ["quantity_product_uom:sum"],
            )
        }
        return incoming, outgoing

    def _build_report_values(self):
        self.ensure_one()
        if self.qty_mode == "done" and self.date_from and self.date_to and self.date_from > self.date_to:
            raise UserError(_("From Date must be before To Date."))

        locations = self._get_report_locations()
        products = self._get_products_for_locations(locations)
        if not products:
            return []

        vals_list = []
        for location in locations:
            location_ids = self._get_expanded_location_ids(location)
            on_hand_map = self._get_on_hand_by_product(location_ids, products)
            if self.qty_mode == "planned":
                incoming_map, outgoing_map = self._get_planned_in_out_by_product(location_ids, products)
            else:
                incoming_map, outgoing_map = self._get_done_in_out_by_product(location_ids, products)

            for product in products:
                on_hand = on_hand_map.get(product.id, 0.0)
                incoming = incoming_map.get(product.id, 0.0)
                outgoing = outgoing_map.get(product.id, 0.0)
                if self.hide_zero_lines and all(
                    float_is_zero(v, precision_rounding=product.uom_id.rounding)
                    for v in (on_hand, incoming, outgoing)
                ):
                    continue
                if self.qty_mode == "planned":
                    forecast = on_hand + incoming - outgoing
                else:
                    # Done IN/OUT are already inside On Hand; forecast stays current stock.
                    forecast = on_hand
                vals_list.append({
                    "qty_mode": self.qty_mode,
                    "location_id": location.id,
                    "product_id": product.id,
                    "qty_on_hand": on_hand,
                    "qty_incoming": incoming,
                    "qty_outgoing": outgoing,
                    "qty_forecast": forecast,
                })
        return vals_list

    def action_generate_report(self):
        self.ensure_one()
        self.line_ids.unlink()
        vals_list = self._build_report_values()
        if not vals_list:
            raise UserError(_("No data found for the selected filters."))
        self.write({"line_ids": [(0, 0, vals) for vals in vals_list]})
        mode_label = dict(self._fields["qty_mode"].selection).get(self.qty_mode)
        return {
            "name": _("Stock Location Quantity Report (%s)", mode_label),
            "type": "ir.actions.act_window",
            "res_model": "stock.location.qty.report.line",
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
        sheet = workbook.add_worksheet(_("Location Qty"))
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
            _("Mode"),
            _("Location"),
            _("Internal Reference"),
            _("Product"),
            _("Unit of Measure"),
            _("On Hand"),
            _("Incoming"),
            _("Outgoing"),
            _("Forecast"),
        ]
        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_style)

        sheet.set_column(0, 0, 22)
        sheet.set_column(1, 1, 35)
        sheet.set_column(2, 2, 18)
        sheet.set_column(3, 3, 45)
        sheet.set_column(4, 4, 16)
        sheet.set_column(5, 8, 14)

        mode_labels = dict(self._fields["qty_mode"].selection)
        row = 1
        for line in self.line_ids.sorted(
            key=lambda rec: (rec.location_id.complete_name or "", rec.product_id.display_name or "")
        ):
            sheet.write(row, 0, mode_labels.get(line.qty_mode, line.qty_mode or ""), text_style)
            sheet.write(row, 1, line.location_name or line.location_id.display_name, text_style)
            sheet.write(row, 2, line.default_code or "", text_style)
            sheet.write(row, 3, line.product_id.display_name, text_style)
            sheet.write(row, 4, line.uom_name or "", text_style)
            sheet.write_number(row, 5, line.qty_on_hand, number_style)
            sheet.write_number(row, 6, line.qty_incoming, number_style)
            sheet.write_number(row, 7, line.qty_outgoing, number_style)
            sheet.write_number(row, 8, line.qty_forecast, number_style)
            row += 1

        workbook.close()
        return output.getvalue()

    def action_export_excel(self):
        self.ensure_one()
        content = self._generate_xlsx_content()
        filename = "stock_location_qty_report.xlsx"
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
