# -*- coding: utf-8 -*-
import base64
import binascii
import csv
import io
import logging
import traceback

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero, float_round

try:
    import xlsxwriter
except ImportError:  # pragma: no cover
    xlsxwriter = None

_logger = logging.getLogger(__name__)

SKU_HEADERS = {"sku", "default_code", "internal_reference", "defaultcode"}
QTY_HEADERS = {"quantity", "qty", "counted", "counted_qty", "count"}
LOCATION_HEADERS = {
    "location",
    "location_name",
    "complete_name",
    "location_id",
    # Odoo export/import style headers (e.g. Google Sheet "Lines/Location")
    "lines/location",
    "lines/location_id",
    "line_ids/location",
    "line_ids/location_id",
    "line_ids/location_id/id",
    "line_ids/location_id/complete_name",
}


class InventoryAsOfBatch(models.Model):
    _name = "inventory.as.of.batch"
    _description = "As-of Inventory Adjustment Batch"
    _order = "create_date desc, id desc"

    name = fields.Char(required=True, copy=False, default="New")
    as_of_datetime = fields.Datetime(
        string="As-of Date",
        required=True,
        help="Date/time used for historical on-hand and for dating inventory moves.",
    )
    location_id = fields.Many2one(
        "stock.location",
        string="Default Location",
        required=True,
        domain="[('usage', 'in', ('internal', 'transit')), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        check_company=True,
        help="Used when the CSV has no location column (or blank location).",
    )
    accounting_date = fields.Date(
        string="Accounting Date",
        help="Date for valuation entries. If empty, the as-of date is used.",
    )
    inventory_reason = fields.Char(
        string="Inventory Reason",
        default="As-of Physical Inventory",
    )
    csv_filename = fields.Char()
    csv_file = fields.Binary(string="CSV File", attachment=True)
    csv_attachment_id = fields.Many2one(
        "ir.attachment",
        string="CSV Attachment",
        ondelete="set null",
        copy=False,
    )
    as_of_stock_xlsx = fields.Binary(
        string="As-of Stock Excel",
        attachment=False,
        copy=False,
        help="Excel of products with on-hand > 0 at the default location on the as-of date.",
    )
    as_of_stock_xlsx_filename = fields.Char(copy=False)
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("ready", "Ready to Review"),
            ("applying", "Applying"),
            ("done", "Done"),
            ("error", "Error"),
        ],
        default="draft",
        required=True,
        index=True,
        copy=False,
    )
    chunk_size = fields.Integer(
        string="Apply Chunk Size",
        default=50,
        help="Number of lines applied per cron tick.",
    )
    line_ids = fields.One2many(
        "inventory.as.of.line",
        "batch_id",
        string="Lines",
    )
    line_count = fields.Integer(compute="_compute_counts", store=True)
    to_apply_count = fields.Integer(compute="_compute_counts", store=True)
    applied_count = fields.Integer(compute="_compute_counts", store=True)
    error_count = fields.Integer(compute="_compute_counts", store=True)
    skip_count = fields.Integer(compute="_compute_counts", store=True)
    missing_count = fields.Integer(
        string="Not On Sheet",
        compute="_compute_counts",
        store=True,
        help="Products that had stock at the default location on the as-of date but were left off the sheet.",
    )
    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
        required=True,
    )
    note = fields.Text()

    @api.depends("line_ids.state", "line_ids.missing_from_sheet")
    def _compute_counts(self):
        for batch in self:
            lines = batch.line_ids
            batch.line_count = len(lines)
            batch.to_apply_count = len(lines.filtered(lambda l: l.state == "to_apply"))
            batch.applied_count = len(lines.filtered(lambda l: l.state == "applied"))
            batch.error_count = len(lines.filtered(lambda l: l.state == "error"))
            batch.skip_count = len(lines.filtered(lambda l: l.state == "skip"))
            batch.missing_count = len(lines.filtered(lambda l: l.missing_from_sheet))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = _("As-of Inventory %s") % fields.Datetime.now()
        return super().create(vals_list)

    def action_load_recompute_lines(self):
        self.ensure_one()
        if self.state == "applying":
            raise UserError(_("Cannot reload lines while the batch is applying."))
        if not self.csv_file and not self.csv_attachment_id:
            raise UserError(_("Upload a CSV file first."))
        if not self.as_of_datetime:
            raise UserError(_("Set the As-of Date."))
        if not self.location_id:
            raise UserError(_("Set the Default Location."))

        rows = self._parse_csv_rows()
        self.line_ids.unlink()
        line_vals = []
        for idx, row in enumerate(rows, start=1):
            line_vals.append(self._prepare_line_vals(idx, row))
        if line_vals:
            self.env["inventory.as.of.line"].create(line_vals)
        self._add_missing_zero_lines()
        self.state = "ready"
        return True

    def action_export_as_of_stock_xlsx(self):
        """Build Excel of products with on-hand > 0 at location on as-of date."""
        self.ensure_one()
        if xlsxwriter is None:
            raise UserError(
                _("The Python library 'xlsxwriter' is required to export Excel files.")
            )
        if not self.as_of_datetime:
            raise UserError(_("Set the As-of Date."))
        if not self.location_id:
            raise UserError(_("Set the Default Location."))

        rows = self._prepare_as_of_stock_rows()
        if not rows:
            raise UserError(
                _(
                    "No products with quantity greater than zero at %(location)s "
                    "on %(date)s."
                )
                % {
                    "location": self.location_id.complete_name,
                    "date": self.as_of_datetime,
                }
            )

        xlsx_bytes = self._build_as_of_stock_xlsx(rows)
        as_of_label = fields.Datetime.to_string(self.as_of_datetime).replace(":", "-")
        location_label = (self.location_id.name or "location").replace("/", "-")
        filename = "As_of_Stock_%s_%s.xlsx" % (location_label, as_of_label)
        # Store on the record (not as a separate attachment) so the binary
        # widget can show the file after the form reloads.
        self.write(
            {
                "as_of_stock_xlsx": base64.b64encode(xlsx_bytes),
                "as_of_stock_xlsx_filename": filename,
            }
        )
        download_url = (
            "/web/content/?model=%s&id=%s&field=as_of_stock_xlsx"
            "&filename_field=as_of_stock_xlsx_filename&download=true"
            % (self._name, self.id)
        )
        # Download without leaving the page, then reload the form so the
        # As-of Stock Excel field shows the saved file.
        return {
            "type": "ir.actions.act_url",
            "url": download_url,
            "target": "download",
            "next": {
                "type": "ir.actions.act_window",
                "name": _("As-of Inventory Adjustment"),
                "res_model": self._name,
                "res_id": self.id,
                "view_mode": "form",
                "views": [(False, "form")],
                "target": "current",
            },
        }

    def _prepare_as_of_stock_rows(self):
        """Return [{name, quantity}] for products with as-of on-hand > 0."""
        self.ensure_one()
        _qty_today_map, qty_as_of_map = self._strict_on_hand_by_product(
            self.location_id, self.as_of_datetime
        )
        positive_ids = [
            product_id
            for product_id, qty in qty_as_of_map.items()
            if qty and qty > 0.0
        ]
        if not positive_ids:
            return []

        products = (
            self.env["product.product"]
            .with_context(active_test=False)
            .browse(positive_ids)
        )
        rows = []
        for product in products.sorted(
            key=lambda p: ((p.display_name or "").lower(), p.id)
        ):
            if not product.is_storable:
                continue
            rounding = product.uom_id.rounding or 0.01
            qty = float_round(
                qty_as_of_map.get(product.id, 0.0), precision_rounding=rounding
            )
            if float_compare(qty, 0.0, precision_rounding=rounding) <= 0:
                continue
            rows.append(
                {
                    "name": product.display_name or product.name or str(product.id),
                    "quantity": qty,
                }
            )
        return rows

    def _build_as_of_stock_xlsx(self, rows):
        self.ensure_one()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        sheet = workbook.add_worksheet(_("As-of Stock"))
        header_format = workbook.add_format({"bold": True})
        qty_format = workbook.add_format({"num_format": "0.00"})

        sheet.write(0, 0, _("Product Name"), header_format)
        sheet.write(0, 1, _("Quantity On Hand"), header_format)
        sheet.set_column(0, 0, 50)
        sheet.set_column(1, 1, 18)

        for index, row in enumerate(rows, start=1):
            sheet.write(index, 0, row["name"])
            sheet.write_number(index, 1, row["quantity"], qty_format)

        workbook.close()
        return output.getvalue()

    def action_confirm_apply(self):
        self.ensure_one()
        if self.state not in ("ready", "error"):
            raise UserError(_("Load and review lines before confirming apply."))
        to_apply = self.line_ids.filtered(lambda l: l.state == "to_apply")
        if not to_apply:
            raise UserError(_("No lines in 'To Apply' state."))
        # Re-queue previous errors that user left as to_apply only.
        self.state = "applying"
        self._trigger_apply_cron()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Applying"),
                "message": _(
                    "%(count)s line(s) queued. Cron will apply them in chunks of %(chunk)s."
                )
                % {"count": len(to_apply), "chunk": self.chunk_size or 50},
                "type": "success",
                "sticky": False,
            },
        }

    def action_reset_draft(self):
        self.ensure_one()
        if self.state == "applying":
            raise UserError(_("Stop applying first or wait until the batch finishes."))
        applied = self.line_ids.filtered(lambda l: l.state == "applied")
        if applied:
            raise UserError(
                _("Cannot reset: %(count)s line(s) already applied.")
                % {"count": len(applied)}
            )
        self.state = "draft"
        return True

    def action_open_lines(self):
        self.ensure_one()
        action = {
            "type": "ir.actions.act_window",
            "name": _("Review Lines"),
            "res_model": "inventory.as.of.line",
            "view_mode": "list,form",
            "domain": [("batch_id", "=", self.id)],
            "context": {
                "default_batch_id": self.id,
                **{
                    key: value
                    for key, value in self.env.context.items()
                    if key.startswith("search_default_")
                },
            },
        }
        return action

    def _trigger_apply_cron(self):
        cron = self.env.ref(
            "pt_inventory_as_of_adjust.ir_cron_inventory_as_of_apply",
            raise_if_not_found=False,
        )
        if cron:
            cron.sudo()._trigger()

    @api.model
    def _cron_apply_queued_batches(self):
        batch = self.search([("state", "=", "applying")], order="id asc", limit=1)
        if not batch:
            return
        batch._apply_next_chunk()

    def _apply_next_chunk(self):
        self.ensure_one()
        chunk_size = self.chunk_size or 50
        lines = self.line_ids.filtered(lambda l: l.state == "to_apply")[:chunk_size]
        if not lines:
            self.state = "error" if self.error_count else "done"
            return

        accounting_date = self.accounting_date or fields.Date.to_date(self.as_of_datetime)
        inventory_name = self.inventory_reason or "As-of Physical Inventory"
        try:
            # One _apply_inventory for the whole chunk → separate stock.move, one journal entry.
            lines._apply_inventory_adjustments(
                as_of_datetime=self.as_of_datetime,
                accounting_date=accounting_date,
                inventory_name=inventory_name,
            )
        except Exception as exc:
            _logger.exception(
                "As-of inventory apply failed for batch %s lines %s",
                self.id,
                lines.ids,
            )
            lines.filtered(lambda l: l.state == "to_apply").write(
                {
                    "state": "error",
                    "error_message": "%s\n%s" % (exc, traceback.format_exc()),
                }
            )
        self.env.cr.commit()

        remaining = self.line_ids.filtered(lambda l: l.state == "to_apply")
        if remaining:
            self._trigger_apply_cron()
        else:
            has_error = bool(self.line_ids.filtered(lambda l: l.state == "error"))
            self.state = "error" if has_error else "done"

    def _parse_csv_rows(self):
        self.ensure_one()
        raw = self._get_csv_raw_bytes()
        if raw[:2] == b"PK":
            raise UserError(
                _("This looks like an Excel file (.xlsx). Save As CSV (UTF-8) and upload again.")
            )
        text = self._decode_csv_bytes(raw)
        reader = self._csv_dict_reader(text)
        if not reader.fieldnames:
            raise UserError(_("CSV has no header row."))

        header_map = self._map_headers(reader.fieldnames)
        if not header_map.get("sku"):
            raise UserError(
                _(
                    "CSV must include an Internal Reference column: "
                    "sku, default_code, or internal_reference."
                )
            )
        if not header_map.get("quantity"):
            raise UserError(_("CSV must include a quantity column."))

        rows = []
        for row in reader:
            if not row:
                continue
            product_key = (row.get(header_map["sku"]) or "").strip()
            qty_raw = (row.get(header_map["quantity"]) or "").strip()
            if not product_key and not qty_raw:
                continue
            location_name = ""
            if header_map.get("location"):
                location_name = (row.get(header_map["location"]) or "").strip()
            rows.append(
                {
                    "product_key": product_key,
                    "quantity": qty_raw,
                    "location": location_name,
                }
            )
        if not rows:
            raise UserError(_("CSV has no data rows."))
        return rows

    def _prepare_line_vals(self, row_number, row):
        self.ensure_one()
        raw_sku = (row.get("product_key") or "").strip()
        location_name = (row.get("location") or "").strip()
        location = self._resolve_location(location_name)
        product = self._resolve_product(raw_sku)
        error_message = False
        state = "to_apply"
        counted_as_of = 0.0
        qty_as_of = 0.0
        qty_today = 0.0
        correction = 0.0
        counted_to_apply = 0.0

        try:
            counted_as_of = self._parse_quantity(row.get("quantity"))
        except UserError as exc:
            state = "error"
            error_message = str(exc)

        if not product:
            state = "error"
            error_message = _(
                "Product not found for Internal Reference '%s' "
                "(exact default_code match required)."
            ) % raw_sku
        elif location_name and not location:
            state = "error"
            error_message = _(
                "Location not found for '%(loc)s'. "
                "Use the full location path (e.g. Salt 1/Stock), or leave blank to use Default Location."
            ) % {"loc": location_name}
        elif not location:
            state = "error"
            error_message = _("Location not found.")
        elif state != "error":
            qty_today = product.with_company(self.company_id).with_context(
                location=location.id,
                company_id=self.company_id.id,
            ).qty_available
            qty_as_of = product.with_company(self.company_id).with_context(
                location=location.id,
                company_id=self.company_id.id,
                to_date=self.as_of_datetime,
            ).qty_available
            correction = counted_as_of - qty_as_of
            counted_to_apply = qty_today + correction
            rounding = product.uom_id.rounding
            if float_is_zero(correction, precision_rounding=rounding):
                state = "skip"

        return {
            "batch_id": self.id,
            "row_number": row_number,
            "raw_sku": raw_sku,
            "product_id": product.id if product else False,
            "location_id": location.id if location else self.location_id.id,
            "counted_as_of": counted_as_of,
            "qty_as_of": qty_as_of,
            "qty_today": qty_today,
            "correction": correction,
            "counted_to_apply": counted_to_apply,
            "state": state,
            "error_message": error_message,
        }

    def _add_missing_zero_lines(self):
        """Add counted-0 lines for stock at the default location left off the sheet.

        Only the batch default location itself is considered. Child locations
        are left alone. A product already present on any sheet line is skipped.
        """
        self.ensure_one()
        location = self.location_id
        if not location or not self.as_of_datetime:
            return

        present_ids = set(self.line_ids.mapped("product_id").ids)
        qty_today_map, qty_as_of_map = self._strict_on_hand_by_product(
            location, self.as_of_datetime
        )
        candidate_ids = [
            product_id
            for product_id, qty in qty_as_of_map.items()
            if product_id not in present_ids and qty > 0.0
        ]
        if not candidate_ids:
            return

        products = (
            self.env["product.product"]
            .with_context(active_test=False)
            .browse(candidate_ids)
        )
        next_row = max(self.line_ids.mapped("row_number") or [0])
        vals_list = []
        for product in products:
            if not product.is_storable:
                continue
            rounding = product.uom_id.rounding or 0.01
            qty_as_of = float_round(
                qty_as_of_map.get(product.id, 0.0), precision_rounding=rounding
            )
            if float_compare(qty_as_of, 0.0, precision_rounding=rounding) <= 0:
                continue
            qty_today = float_round(
                qty_today_map.get(product.id, 0.0), precision_rounding=rounding
            )
            correction = float_round(-qty_as_of, precision_rounding=rounding)
            next_row += 1
            vals_list.append(
                {
                    "batch_id": self.id,
                    "row_number": next_row,
                    "raw_sku": product.default_code or str(product.id),
                    "product_id": product.id,
                    "location_id": location.id,
                    "counted_as_of": 0.0,
                    "qty_as_of": qty_as_of,
                    "qty_today": qty_today,
                    "correction": correction,
                    "counted_to_apply": float_round(
                        qty_today + correction, precision_rounding=rounding
                    ),
                    "state": "to_apply",
                    "missing_from_sheet": True,
                }
            )
        if not vals_list:
            return

        Line = self.env["inventory.as.of.line"]
        for start in range(0, len(vals_list), 500):
            Line.create(vals_list[start : start + 500])
        _logger.info(
            "As-of batch %s added %s not-on-sheet line(s) at %s as of %s",
            self.id,
            len(vals_list),
            location.complete_name,
            self.as_of_datetime,
        )

    def _strict_on_hand_by_product(self, location, as_of_datetime):
        """Return (qty_today, qty_as_of) maps for this location only.

        Child locations are excluded. The as-of figure rewinds done moves
        after that datetime, matching qty_available with strict=True and to_date.
        """
        self.ensure_one()
        company_ids = [self.company_id.id, False]
        Quant = (
            self.env["stock.quant"]
            .with_company(self.company_id)
            .with_context(active_test=False)
        )
        Move = (
            self.env["stock.move"]
            .with_company(self.company_id)
            .with_context(active_test=False)
        )
        quant_domain = [
            ("location_id", "=", location.id),
            ("company_id", "in", company_ids),
            ("product_id.is_storable", "=", True),
        ]
        qty_today = {}
        for product, quantity in Quant._read_group(
            quant_domain, ["product_id"], ["quantity:sum"]
        ):
            if product:
                qty_today[product.id] = quantity or 0.0

        qty_as_of = dict(qty_today)
        as_of = fields.Datetime.to_datetime(as_of_datetime)
        if as_of and as_of < fields.Datetime.now():
            move_base = [
                ("state", "=", "done"),
                ("date", ">", as_of),
                ("company_id", "in", company_ids),
                ("product_id.is_storable", "=", True),
            ]
            for product, qty in Move._read_group(
                move_base
                + [
                    ("location_dest_id", "=", location.id),
                    ("location_id", "!=", location.id),
                ],
                ["product_id"],
                ["product_qty:sum"],
            ):
                if product:
                    qty_as_of[product.id] = qty_as_of.get(product.id, 0.0) - (qty or 0.0)
            for product, qty in Move._read_group(
                move_base
                + [
                    ("location_id", "=", location.id),
                    ("location_dest_id", "!=", location.id),
                ],
                ["product_id"],
                ["product_qty:sum"],
            ):
                if product:
                    qty_as_of[product.id] = qty_as_of.get(product.id, 0.0) + (qty or 0.0)
        return qty_today, qty_as_of

    def _resolve_product(self, raw_key):
        """Match only by exact Internal Reference (default_code)."""
        if not raw_key:
            return self.env["product.product"]
        return self.env["product.product"].search(
            [("default_code", "=", raw_key)], limit=1
        )

    def _company_location_domain(self, extra_domain=None):
        """Restrict locations to the batch company (or shared company-less locs)."""
        self.ensure_one()
        domain = [
            "|",
            ("company_id", "=", False),
            ("company_id", "=", self.company_id.id),
        ]
        if extra_domain:
            domain = list(extra_domain) + domain
        return domain

    def _resolve_location(self, location_name):
        self.ensure_one()
        if not location_name:
            return self.location_id
        Location = self.env["stock.location"]
        base = self._company_location_domain(
            [("usage", "in", ("internal", "transit"))]
        )
        # Exact complete name (preferred): "Salt 1/Stock"
        location = Location.search(
            [("complete_name", "=", location_name)] + base,
            limit=1,
        )
        if location:
            return location
        # Ends-with match helps when sheet has short or slightly different path.
        location = Location.search(
            [("complete_name", "=ilike", "%%%s" % location_name)] + base,
            limit=1,
        )
        if location:
            return location
        location = Location.search(
            [("complete_name", "ilike", location_name)] + base,
            limit=1,
        )
        if location:
            return location
        location = Location.search(
            [("name", "=", location_name)] + base,
            limit=1,
        )
        if location:
            return location
        # External id / xml id style (rare in sheets)
        if "." in location_name and "/" not in location_name:
            try:
                return self.env.ref(location_name)
            except ValueError:
                pass
        _logger.warning(
            "As-of CSV location not found: %r (batch=%s company=%s) → using default %s",
            location_name,
            self.id,
            self.company_id.display_name,
            self.location_id.complete_name,
        )
        return self.env["stock.location"]

    @api.model
    def _parse_quantity(self, value):
        if value in (None, False, ""):
            raise UserError(_("Missing quantity."))
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip().replace(",", "")
        try:
            return float(text)
        except ValueError as exc:
            raise UserError(_("Invalid quantity: %s") % value) from exc

    @api.model
    def _normalize_header(self, name):
        """Normalize CSV header: 'Lines/Location' -> 'lines/location'."""
        key = str(name or "").strip().lower()
        key = key.replace(" ", "_").replace("\\", "/")
        while "__" in key:
            key = key.replace("__", "_")
        return key

    @api.model
    def _map_headers(self, fieldnames):
        mapping = {}
        for name in fieldnames or []:
            if not name:
                continue
            key = self._normalize_header(name)
            # Also accept bare last segment: "foo/location" -> try "location"
            last = key.rsplit("/", 1)[-1]
            if key in SKU_HEADERS or last in SKU_HEADERS:
                if "sku" not in mapping:
                    mapping["sku"] = name
            elif key in QTY_HEADERS or last in QTY_HEADERS:
                if "quantity" not in mapping:
                    mapping["quantity"] = name
            elif key in LOCATION_HEADERS or last in LOCATION_HEADERS:
                if "location" not in mapping:
                    mapping["location"] = name
        return mapping

    def _get_csv_raw_bytes(self):
        self.ensure_one()
        if self.csv_file:
            raw = self.csv_file
            if isinstance(raw, bytes):
                try:
                    return base64.b64decode(raw, validate=False)
                except (binascii.Error, ValueError):
                    return raw
            if isinstance(raw, str):
                try:
                    return base64.b64decode(raw, validate=False)
                except (binascii.Error, ValueError):
                    return raw.encode("utf-8")
        if self.csv_attachment_id:
            att = self.csv_attachment_id
            raw = att.raw
            if raw:
                return raw if isinstance(raw, bytes) else base64.b64decode(raw)
            if att.datas:
                return base64.b64decode(att.datas)
        raise UserError(_("Upload a CSV file first."))

    @api.model
    def _decode_csv_bytes(self, raw):
        if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
            try:
                return raw.decode("utf-16")
            except UnicodeDecodeError:
                pass
        for encoding in (
            "utf-8-sig",
            "utf-8",
            "utf-16",
            "utf-16-le",
            "utf-16-be",
            "cp1256",
            "cp1252",
            "latin-1",
        ):
            try:
                text = raw.decode(encoding)
                if encoding.startswith("utf-8") and text.count("\x00") > max(4, len(text) // 20):
                    continue
                return text
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")

    @api.model
    def _csv_dict_reader(self, text):
        best_delimiter = ","
        best_cols = 0
        for delimiter in (",", ";", "\t", "|"):
            reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
            if not reader.fieldnames:
                continue
            ncol = len([name for name in reader.fieldnames if name and str(name).strip()])
            if ncol > best_cols:
                best_cols = ncol
                best_delimiter = delimiter
        return csv.DictReader(io.StringIO(text), delimiter=best_delimiter)
