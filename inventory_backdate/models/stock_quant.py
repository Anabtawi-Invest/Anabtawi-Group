from datetime import datetime, timezone

from odoo import api, fields, models
from odoo.tools.misc import groupby


class StockQuant(models.Model):
    _inherit = "stock.quant"

    backdate_reason = fields.Char(
        string="Backdate Reason",
        help="Optional reason for applying this inventory adjustment on a past Accounting Date.",
        copy=False,
    )
    quantity_at_date = fields.Float(
        string="Qty at Date",
        compute="_compute_historical_inventory",
        digits="Product Unit of Measure",
        help="On-hand quantity of this product in this location as of the Accounting Date, "
             "after replaying all earlier in/out moves.",
    )
    quantity_after_date = fields.Float(
        string="Later In/Out",
        compute="_compute_historical_inventory",
        digits="Product Unit of Measure",
        help="Net quantity of done in/out moves after the Accounting Date (in minus out).",
    )
    expected_quantity = fields.Float(
        string="On Hand After Apply",
        compute="_compute_historical_inventory",
        digits="Product Unit of Measure",
        help="Expected on-hand today after apply: counted quantity at date + later in/out moves.",
    )

    @api.model
    def _get_inventory_fields_write(self):
        fields_list = super()._get_inventory_fields_write()
        fields_list.append("backdate_reason")
        return fields_list

    @api.model
    def _inventory_backdate_datetime(self, accounting_date):
        """Convert a Date to end-of-day in the user timezone, or keep a Datetime as-is."""
        if not accounting_date:
            return False
        if isinstance(accounting_date, datetime):
            return fields.Datetime.to_datetime(accounting_date)
        accounting_date = fields.Date.to_date(accounting_date)
        now_local = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        local_dt = now_local.replace(
            year=accounting_date.year,
            month=accounting_date.month,
            day=accounting_date.day,
            hour=23,
            minute=59,
            second=59,
            microsecond=0,
        )
        return local_dt.astimezone(timezone.utc).replace(tzinfo=None)

    def _move_line_qty_in_product_uom(self, line):
        if "quantity_product_uom" in line._fields:
            return line.quantity_product_uom
        return line.product_uom_id._compute_quantity(
            line.quantity, line.product_id.uom_id, rounding_method="HALF-UP"
        )

    def _get_subsequent_move_qty(self, at_dt):
        """Net done quantity (in - out) for this quant after `at_dt`."""
        self.ensure_one()
        domain = [
            ("product_id", "=", self.product_id.id),
            ("state", "=", "done"),
            ("date", ">", at_dt),
            ("company_id", "=", (self.company_id or self.env.company).id),
            "|",
            ("location_id", "=", self.location_id.id),
            ("location_dest_id", "=", self.location_id.id),
        ]
        if self.lot_id:
            domain.append(("lot_id", "=", self.lot_id.id))
        else:
            domain.append(("lot_id", "=", False))
        if self.owner_id:
            domain.append(("owner_id", "=", self.owner_id.id))
        else:
            domain.append(("owner_id", "=", False))

        net = 0.0
        for line in self.env["stock.move.line"].sudo().search(domain):
            qty = self._move_line_qty_in_product_uom(line)
            incoming = line.location_dest_id == self.location_id
            package = line.result_package_id if incoming else line.package_id
            if package != self.package_id:
                continue
            net += qty if incoming else -qty
        return net

    def _get_quantity_at_date(self, at_dt):
        """Current on-hand minus later in/out = quantity as of `at_dt`."""
        self.ensure_one()
        return self.quantity - self._get_subsequent_move_qty(at_dt)

    @api.depends(
        "accounting_date",
        "quantity",
        "inventory_quantity",
        "inventory_quantity_set",
        "product_id",
        "location_id",
        "lot_id",
        "package_id",
        "owner_id",
    )
    def _compute_historical_inventory(self):
        for quant in self:
            if not quant.accounting_date:
                quant.quantity_at_date = quant.quantity
                quant.quantity_after_date = 0.0
                quant.expected_quantity = (
                    quant.inventory_quantity if quant.inventory_quantity_set else quant.quantity
                )
                continue
            as_of = quant._inventory_backdate_datetime(quant.accounting_date)
            later_net = quant._get_subsequent_move_qty(as_of)
            qty_at_date = quant.quantity - later_net
            counted = quant.inventory_quantity if quant.inventory_quantity_set else qty_at_date
            quant.quantity_after_date = later_net
            quant.quantity_at_date = qty_at_date
            quant.expected_quantity = counted + later_net

    @api.depends(
        "inventory_quantity",
        "inventory_quantity_set",
        "quantity",
        "accounting_date",
        "product_id",
        "location_id",
        "lot_id",
        "package_id",
        "owner_id",
    )
    def _compute_inventory_diff_quantity(self):
        historical = self.filtered(lambda quant: quant.accounting_date and quant.inventory_quantity_set)
        super(StockQuant, self - historical)._compute_inventory_diff_quantity()
        for quant in historical:
            as_of = quant._inventory_backdate_datetime(quant.accounting_date)
            qty_at_date = quant._get_quantity_at_date(as_of)
            quant.inventory_diff_quantity = quant.inventory_quantity - qty_at_date

    def _apply_inventory(self, date=None):
        if date is not None or not any(self.mapped("accounting_date")):
            reason = next((r for r in self.mapped("backdate_reason") if r), "")
            ctx = {"inventory_backdate_from_quant": True}
            if reason:
                ctx["inventory_backdate_reason"] = reason
            return super(StockQuant, self.with_context(**ctx))._apply_inventory(date)

        for accounting_date, inventory_ids in groupby(self, key=lambda quant: quant.accounting_date):
            inventories = self.env["stock.quant"].concat(*inventory_ids)
            reason = next((r for r in inventories.mapped("backdate_reason") if r), "")
            apply_date = date
            if accounting_date:
                apply_date = inventories._inventory_backdate_datetime(accounting_date)
                inventories.invalidate_recordset([
                    "inventory_diff_quantity",
                    "quantity_at_date",
                    "quantity_after_date",
                    "expected_quantity",
                ])
            inventories = inventories.with_context(
                inventory_backdate_from_quant=True,
                inventory_backdate_reason=reason,
                force_effective_datetime=apply_date,
            )
            super(StockQuant, inventories)._apply_inventory(apply_date)
