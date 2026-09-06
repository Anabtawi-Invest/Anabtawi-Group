from odoo import api, fields, models


class StockInventoryAdjustmentName(models.TransientModel):
    _inherit = "stock.inventory.adjustment.name"

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        quant_ids = self.env.context.get("default_quant_ids") or []
        quants = self.env["stock.quant"].browse(quant_ids)
        accounting_dates = [date for date in quants.mapped("accounting_date") if date]
        if accounting_dates and "counting_date" in self._fields:
            res["counting_date"] = self.env["stock.quant"]._inventory_backdate_datetime(
                accounting_dates[0]
            )
        return res

    def action_apply(self):
        quants = self.quant_ids.filtered("inventory_quantity_set")
        if any(quants.mapped("accounting_date")):
            return quants.with_context(self._get_quants_context()).action_apply_inventory()
        return super().action_apply()
