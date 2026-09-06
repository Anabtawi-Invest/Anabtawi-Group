from datetime import timezone

from odoo import api, fields, models, _
from odoo.tools.misc import groupby


class StockQuant(models.Model):
    _inherit = "stock.quant"

    backdate_reason = fields.Char(
        string="Backdate Reason",
        help="Optional reason for applying this inventory adjustment on a past Accounting Date.",
        copy=False,
    )

    @api.model
    def _get_inventory_fields_write(self):
        fields_list = super()._get_inventory_fields_write()
        fields_list.append("backdate_reason")
        return fields_list

    @api.model
    def _inventory_backdate_datetime(self, accounting_date):
        """Keep the current clock time, on the chosen accounting date, in the user timezone."""
        accounting_date = fields.Date.to_date(accounting_date)
        now_local = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        local_dt = now_local.replace(
            year=accounting_date.year,
            month=accounting_date.month,
            day=accounting_date.day,
        )
        return local_dt.astimezone(timezone.utc).replace(tzinfo=None)

    def _apply_inventory(self, date=None):
        if date is not None or not any(self.mapped("accounting_date")):
            reason = next((r for r in self.mapped("backdate_reason") if r), "")
            if reason:
                self = self.with_context(inventory_backdate_reason=reason)
            return super()._apply_inventory(date)

        for accounting_date, inventory_ids in groupby(self, key=lambda quant: quant.accounting_date):
            inventories = self.env["stock.quant"].concat(*inventory_ids)
            reason = next((r for r in inventories.mapped("backdate_reason") if r), "")
            inventories = inventories.with_context(inventory_backdate_reason=reason)
            apply_date = date
            if accounting_date:
                apply_date = inventories._inventory_backdate_datetime(accounting_date)
            super(StockQuant, inventories)._apply_inventory(apply_date)
