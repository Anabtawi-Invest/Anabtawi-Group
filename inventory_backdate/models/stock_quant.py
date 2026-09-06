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
        help="On-hand quantity of this product in this location as of the Accounting Date.",
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

    def _get_quantity_at_date(self, at_dt):
        """Quantity in this exact location as of `at_dt`, using Odoo's stock history."""
        self.ensure_one()
        if not self.product_id or not self.location_id:
            return 0.0
        ctx = {
            "to_date": at_dt,
            "location": self.location_id.id,
            "strict": True,
            "lot_id": self.lot_id.id if self.lot_id else False,
            "owner_id": self.owner_id.id if self.owner_id else False,
            "package_id": self.package_id.id if self.package_id else False,
        }
        return self.product_id.with_company(self.company_id or self.env.company).with_context(**ctx).qty_available

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
            qty_at_date = quant._get_quantity_at_date(as_of)
            later_net = quant.quantity - qty_at_date
            counted = quant.inventory_quantity if quant.inventory_quantity_set else qty_at_date
            quant.quantity_at_date = qty_at_date
            quant.quantity_after_date = later_net
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
        # The Apply wizard always passes counting_date=now. That must not override Accounting Date.
        backdated = self.filtered(lambda quant: quant.accounting_date)
        rest = self - backdated
        if rest:
            super(StockQuant, rest)._apply_inventory(date)

        for accounting_date, inventory_ids in groupby(backdated, key=lambda quant: quant.accounting_date):
            inventories = self.env["stock.quant"].concat(*inventory_ids)
            reason = next((r for r in inventories.mapped("backdate_reason") if r), "")
            apply_date = inventories._inventory_backdate_datetime(accounting_date)
            inventories.invalidate_recordset([
                "inventory_diff_quantity",
                "quantity_at_date",
                "quantity_after_date",
                "expected_quantity",
            ])
            super(StockQuant, inventories.with_context(
                inventory_backdate_from_quant=True,
                inventory_backdate_reason=reason,
                force_effective_datetime=apply_date,
                force_period_date=accounting_date,
            ))._apply_inventory(apply_date)
