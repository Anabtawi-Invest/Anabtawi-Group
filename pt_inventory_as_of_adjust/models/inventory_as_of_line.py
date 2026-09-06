# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_is_zero


class InventoryAsOfLine(models.Model):
    _name = "inventory.as.of.line"
    _description = "As-of Inventory Adjustment Line"
    _order = "row_number, id"

    batch_id = fields.Many2one(
        "inventory.as.of.batch",
        required=True,
        ondelete="cascade",
        index=True,
    )
    row_number = fields.Integer(index=True)
    raw_sku = fields.Char(string="SKU / Barcode")
    product_id = fields.Many2one("product.product", string="Product", index=True)
    location_id = fields.Many2one(
        "stock.location",
        string="Location",
        required=True,
        domain="[('usage', 'in', ('internal', 'transit'))]",
    )
    counted_as_of = fields.Float(string="Counted As Of", digits="Product Unit")
    qty_as_of = fields.Float(
        string="On Hand As Of",
        digits="Product Unit",
        readonly=True,
    )
    qty_today = fields.Float(
        string="On Hand Today",
        digits="Product Unit",
        readonly=True,
    )
    correction = fields.Float(
        string="Correction",
        digits="Product Unit",
        readonly=True,
    )
    counted_to_apply = fields.Float(
        string="Counted To Apply",
        digits="Product Unit",
        readonly=True,
    )
    state = fields.Selection(
        selection=[
            ("to_apply", "To Apply"),
            ("skip", "Skip"),
            ("applied", "Applied"),
            ("error", "Error"),
        ],
        default="to_apply",
        required=True,
        index=True,
    )
    note = fields.Char()
    error_message = fields.Text()
    company_id = fields.Many2one(related="batch_id.company_id", store=True)

    def write(self, vals):
        res = super().write(vals)
        if "counted_as_of" in vals or "location_id" in vals or "product_id" in vals:
            self._recompute_correction_fields()
        elif "state" in vals:
            # Keep skip/to_apply consistent when user toggles after editing qty.
            pass
        return res

    def _recompute_correction_fields(self):
        for line in self:
            if line.state == "applied":
                continue
            if not line.product_id or not line.location_id or not line.batch_id.as_of_datetime:
                continue
            product = line.product_id
            location = line.location_id
            company = line.batch_id.company_id
            qty_today = product.with_company(company).with_context(
                location=location.id,
                company_id=company.id,
            ).qty_available
            qty_as_of = product.with_company(company).with_context(
                location=location.id,
                company_id=company.id,
                to_date=line.batch_id.as_of_datetime,
            ).qty_available
            correction = line.counted_as_of - qty_as_of
            counted_to_apply = qty_today + correction
            rounding = product.uom_id.rounding
            new_state = line.state
            if line.state in ("to_apply", "skip", "error") and line.product_id:
                if float_is_zero(correction, precision_rounding=rounding):
                    new_state = "skip"
                elif line.state == "skip":
                    new_state = "to_apply"
                elif line.state == "error" and not line.error_message:
                    new_state = "to_apply"
            super(InventoryAsOfLine, line).write(
                {
                    "qty_as_of": qty_as_of,
                    "qty_today": qty_today,
                    "correction": correction,
                    "counted_to_apply": counted_to_apply,
                    "state": new_state,
                    "error_message": False if new_state != "error" else line.error_message,
                }
            )

    def action_mark_skip(self):
        self.filtered(lambda l: l.state in ("to_apply", "error")).write({"state": "skip"})

    def action_mark_to_apply(self):
        for line in self.filtered(lambda l: l.state in ("skip", "error")):
            if not line.product_id:
                continue
            rounding = line.product_id.uom_id.rounding
            if float_is_zero(line.correction, precision_rounding=rounding):
                continue
            line.write({"state": "to_apply", "error_message": False})

    def _apply_inventory_adjustment(self, as_of_datetime, accounting_date, inventory_name):
        self.ensure_one()
        if self.state != "to_apply":
            return
        if not self.product_id or not self.location_id:
            raise UserError(_("Line %(row)s is missing product or location.") % {"row": self.row_number})

        product = self.product_id
        location = self.location_id
        Quant = self.env["stock.quant"].with_context(inventory_mode=True).sudo()
        quant = Quant.search(
            [
                ("product_id", "=", product.id),
                ("location_id", "=", location.id),
                ("lot_id", "=", False),
                ("package_id", "=", False),
                ("owner_id", "=", False),
            ],
            limit=1,
        )
        if not quant:
            quant = Quant.create(
                {
                    "product_id": product.id,
                    "location_id": location.id,
                    "inventory_quantity": self.counted_to_apply,
                }
            )
        else:
            quant.inventory_quantity = self.counted_to_apply

        if accounting_date:
            quant.accounting_date = accounting_date

        ctx = {
            "inventory_name": inventory_name,
            "force_period_date": accounting_date,
        }
        # Prefer direct apply to avoid conflict wizard in cron.
        quant.with_context(**ctx)._apply_inventory(as_of_datetime)
        self.write({"state": "applied", "error_message": False})
