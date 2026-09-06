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
        string="System Qty at Date",
        compute="_compute_historical_inventory",
        digits="Product Unit of Measure",
        help="What the system had in this location as of the Accounting Date (all in/out up to that date).",
    )
    quantity_after_date = fields.Float(
        string="Later In/Out",
        compute="_compute_historical_inventory",
        digits="Product Unit of Measure",
        help="Net in/out after the Accounting Date. Example: an out of 3 later = -3.",
    )
    expected_quantity = fields.Float(
        string="On Hand After Apply",
        compute="_compute_historical_inventory",
        digits="Product Unit of Measure",
        help="Counted qty at date + later in/out. Example: 10 counted on 01/09, then out 3 → 7 today.",
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

    def _move_line_qty(self, line):
        if "quantity_product_uom" in line._fields:
            return line.quantity_product_uom
        return line.product_uom_id._compute_quantity(
            line.quantity, line.product_id.uom_id, rounding_method="HALF-UP"
        )

    def _get_quantity_at_date(self, at_dt):
        """Rebuild on-hand from done in/out lines in this location up to `at_dt`.

        Example: no moves before 01/09 → 0, even if today's quant is already -3.
        """
        self.ensure_one()
        if not self.product_id or not self.location_id or not at_dt:
            return 0.0

        domain = [
            ("product_id", "=", self.product_id.id),
            ("move_id.state", "=", "done"),
            "|",
            ("location_id", "=", self.location_id.id),
            ("location_dest_id", "=", self.location_id.id),
        ]
        if self.company_id:
            domain.append(("company_id", "=", self.company_id.id))
        if self.lot_id:
            domain.append(("lot_id", "=", self.lot_id.id))

        net = 0.0
        for line in self.env["stock.move.line"].sudo().search(domain):
            line_date = line.date or line.move_id.date
            if not line_date or line_date > at_dt:
                continue
            if line.location_id == line.location_dest_id:
                continue
            incoming = line.location_dest_id.id == self.location_id.id
            package = line.result_package_id if incoming else line.package_id
            if self.package_id:
                if package != self.package_id:
                    continue
            elif package:
                continue
            if self.owner_id:
                if line.owner_id != self.owner_id:
                    continue
            elif line.owner_id:
                continue
            qty = self._move_line_qty(line)
            net += qty if incoming else -qty
        return net

    def _get_historical_inventory_diff(self):
        """Counted as of Accounting Date minus what the system had on that date."""
        self.ensure_one()
        as_of = self._inventory_backdate_datetime(self.accounting_date)
        qty_at_date = self._get_quantity_at_date(as_of)
        return self.inventory_quantity - qty_at_date

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
            quant.inventory_diff_quantity = quant._get_historical_inventory_diff()

    def _get_inventory_loss_location(self, default_loss_locations):
        self.ensure_one()
        return self.product_id.with_company(self.company_id).property_stock_inventory or default_loss_locations.get(
            self.company_id.id
        )

    def _apply_historical_inventory(self):
        """Apply counted qty as of Accounting Date, then keep later in/out on top.

        01/09 system 0, counted 10, then out 3 on 04/09 → create +10 on 01/09, today = 7.
        """
        self.inventory_quantity_set = True
        default_loss_locations = {}
        missing_loss = self.filtered(
            lambda quant: not quant.product_id.with_company(quant.company_id).property_stock_inventory
        )
        for company in missing_loss.mapped("company_id"):
            loss_location_id = self.env["ir.default"].with_company(company)._get_model_defaults(
                "product.template"
            ).get("property_stock_inventory")
            default_loss_locations[company.id] = self.env["stock.location"].browse(loss_location_id)

        for accounting_date, inventory_ids in groupby(self, key=lambda quant: quant.accounting_date):
            inventories = self.env["stock.quant"].concat(*inventory_ids)
            reason = next((r for r in inventories.mapped("backdate_reason") if r), "")
            apply_date = inventories._inventory_backdate_datetime(accounting_date)
            move_vals = []
            for quant in inventories:
                if self.env.context.get("from_inverse_qty") and quant.product_uom_id.compare(
                    quant.inventory_diff_quantity, 0
                ) == 0:
                    continue
                diff = quant._get_historical_inventory_diff()
                if quant.product_uom_id.is_zero(diff):
                    continue
                inventory_location = quant._get_inventory_loss_location(default_loss_locations)
                if quant.product_uom_id.compare(diff, 0) > 0:
                    move_vals.append(
                        quant._get_inventory_move_values(
                            diff,
                            inventory_location,
                            quant.location_id,
                            package_dest_id=quant.package_id,
                        )
                    )
                else:
                    move_vals.append(
                        quant._get_inventory_move_values(
                            -diff,
                            quant.location_id,
                            inventory_location,
                            package_id=quant.package_id,
                        )
                    )

            backdate_ctx = {
                "inventory_mode": False,
                "inventory_backdate_from_quant": True,
                "inventory_backdate_reason": reason,
                "force_period_date": accounting_date,
                "force_effective_datetime": apply_date,
            }
            if move_vals:
                moves = self.env["stock.move"].with_context(**backdate_ctx).create(move_vals)
                moves.with_context(ignore_dest_packages=True, **backdate_ctx)._action_done()
                moves.write({"date": apply_date, "is_backdated": True})
                moves._trigger_assign()

            inventories.accounting_date = False

        self.location_id.sudo().write({"last_inventory_date": fields.Date.today()})
        date_by_location = {loc: loc._get_next_inventory_date() for loc in self.mapped("location_id")}
        for quant in self:
            quant.inventory_date = date_by_location[quant.location_id]
        self.action_clear_inventory_quantity()

    def _apply_inventory(self, date=None):
        backdated = self.filtered(lambda quant: quant.accounting_date)
        rest = self - backdated
        if rest:
            super(StockQuant, rest)._apply_inventory(date)
        if backdated:
            backdated._apply_historical_inventory()
