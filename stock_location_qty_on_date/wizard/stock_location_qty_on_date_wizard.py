# -*- coding: utf-8 -*-
import base64
import io
from datetime import datetime, time

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_is_zero

try:
    import xlsxwriter
except ImportError:  # pragma: no cover
    xlsxwriter = None


class StockLocationQtyOnDateWizard(models.TransientModel):
    _name = "stock.location.qty.on.date.wizard"
    _description = "Location Quantity on Hand"

    stock_date = fields.Date(
        string="Date",
        required=True,
        default=fields.Date.context_today,
    )
    all_locations = fields.Boolean(
        string="All Locations",
        default=True,
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Location",
        domain="[('usage', '=', 'internal')]",
    )
    all_products = fields.Boolean(
        string="All Products",
        default=True,
    )
    product_ids = fields.Many2many(
        "product.product",
        "stock_location_qty_on_date_wiz_product_rel",
        "wizard_id",
        "product_id",
        string="Products",
        domain="[('is_storable', '=', True)]",
    )
    file_data = fields.Binary(string="File", readonly=True)
    filename = fields.Char(string="Filename", readonly=True)

    @api.onchange("all_locations")
    def _onchange_all_locations(self):
        if self.all_locations:
            self.location_id = False

    @api.onchange("all_products")
    def _onchange_all_products(self):
        if self.all_products:
            self.product_ids = [(5, 0, 0)]

    def action_export_xlsx(self):
        self.ensure_one()
        if xlsxwriter is None:
            raise UserError(_("The Python library 'xlsxwriter' is required to export Excel files."))

        rows = self._prepare_rows()
        if not rows:
            raise UserError(_("No on-hand quantity was found for this date."))

        xlsx_bytes = self._build_xlsx(rows)
        fname = "Location_Qty_%s.xlsx" % self.stock_date
        self.write({
            "file_data": base64.b64encode(xlsx_bytes),
            "filename": fname,
        })
        return {
            "type": "ir.actions.act_url",
            "url": (
                "/web/content/?model=%s&id=%s&field=file_data"
                "&filename_field=filename&download=true"
            ) % (self._name, self.id),
            "target": "self",
        }

    def _get_locations(self):
        self.ensure_one()
        if self.all_locations:
            locations = self.env["stock.location"].search([
                ("usage", "=", "internal"),
                ("company_id", "in", self.env.companies.ids + [False]),
            ], order="complete_name, id")
            if not locations:
                raise UserError(_("No internal locations were found."))
            return locations
        if not self.location_id:
            raise UserError(_("Select a location, or keep All Locations checked."))
        return self.location_id

    def _get_product_domain(self):
        self.ensure_one()
        domain = [("product_id.is_storable", "=", True)]
        if not self.all_products:
            if not self.product_ids:
                raise UserError(_("Select at least one product, or keep All Products checked."))
            products = self.product_ids.filtered("is_storable")
            if not products:
                raise UserError(_("The selected products are not storable."))
            domain.append(("product_id", "in", products.ids))
        return domain

    def _as_of_datetime(self):
        """End of the selected day in the user's timezone, as a naive UTC datetime."""
        self.ensure_one()
        tz_name = self.env.user.tz or "UTC"
        try:
            timezone = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            timezone = pytz.UTC
        local_end = timezone.localize(datetime.combine(self.stock_date, time.max))
        return local_end.astimezone(pytz.UTC).replace(tzinfo=None)

    def _qty_by_location_product(self, locations):
        """On-hand at the end of the selected day, per exact location and product.

        Matches product.qty_available with to_date: today's stock.quant quantity,
        minus done receipts after that datetime, plus done issues after it.
        Each location is its own balance. A transfer between two locations is
        removed from the source and added to the destination.
        """
        self.ensure_one()
        location_ids = locations.ids
        company_ids = self.env.companies.ids + [False]
        product_domain = self._get_product_domain()
        Quant = self.env["stock.quant"].with_context(active_test=False)
        Move = self.env["stock.move"].with_context(active_test=False)

        qty = {}
        quant_domain = [
            ("location_id", "in", location_ids),
            ("company_id", "in", company_ids),
        ] + product_domain
        for location, product, quantity in Quant._read_group(
            quant_domain,
            ["location_id", "product_id"],
            ["quantity:sum"],
        ):
            if location and product:
                qty[(location.id, product.id)] = quantity or 0.0

        as_of = self._as_of_datetime()
        if as_of < fields.Datetime.now():
            move_base = [
                ("state", "=", "done"),
                ("date", ">", as_of),
                ("company_id", "in", company_ids),
            ] + product_domain
            for location, product, moved in Move._read_group(
                move_base + [("location_dest_id", "in", location_ids)],
                ["location_dest_id", "product_id"],
                ["product_qty:sum"],
            ):
                if location and product and location.id in location_ids:
                    key = (location.id, product.id)
                    qty[key] = qty.get(key, 0.0) - (moved or 0.0)
            for location, product, moved in Move._read_group(
                move_base + [("location_id", "in", location_ids)],
                ["location_id", "product_id"],
                ["product_qty:sum"],
            ):
                if location and product and location.id in location_ids:
                    key = (location.id, product.id)
                    qty[key] = qty.get(key, 0.0) + (moved or 0.0)
        return qty

    def _prepare_rows(self):
        self.ensure_one()
        locations = self._get_locations()
        qty_map = self._qty_by_location_product(locations)
        if not qty_map:
            return []

        products = self.env["product.product"].browse({
            product_id for (_location_id, product_id) in qty_map
        })
        product_by_id = {product.id: product for product in products}
        location_by_id = {location.id: location for location in locations}

        rows = []
        for (location_id, product_id), quantity in qty_map.items():
            product = product_by_id.get(product_id)
            location = location_by_id.get(location_id)
            if not product or not location:
                continue
            rounding = product.uom_id.rounding or 0.01
            if float_is_zero(quantity, precision_rounding=rounding):
                continue
            rows.append({
                "location": location.complete_name,
                "product": product.display_name,
                "quantity": quantity,
            })
        rows.sort(key=lambda row: (row["location"], row["product"]))
        return rows

    def _build_xlsx(self, rows):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet(_("On Hand"))
        sheet.freeze_panes(2, 0)

        qty_digits = self.env["decimal.precision"].precision_get("Product Unit of Measure")
        qty_format = "#,##0" if qty_digits <= 0 else "#,##0." + ("0" * qty_digits)

        title_style = workbook.add_format({"bold": True})
        header_style = workbook.add_format({
            "bold": True,
            "bg_color": "#D9E1F2",
            "border": 1,
            "align": "center",
        })
        text_style = workbook.add_format({"border": 1})
        number_style = workbook.add_format({"border": 1, "num_format": qty_format})

        sheet.write(0, 0, _("Date"), title_style)
        sheet.write(0, 1, self.stock_date.strftime("%Y-%m-%d"), title_style)

        headers = [_("Location"), _("Product"), _("Quantity on Hand")]
        for col, header in enumerate(headers):
            sheet.write(1, col, header, header_style)

        for row_idx, row in enumerate(rows, start=2):
            sheet.write(row_idx, 0, row["location"], text_style)
            sheet.write(row_idx, 1, row["product"], text_style)
            sheet.write_number(row_idx, 2, row["quantity"], number_style)

        sheet.set_column(0, 0, 40)
        sheet.set_column(1, 1, 45)
        sheet.set_column(2, 2, 20)
        workbook.close()
        return output.getvalue()
