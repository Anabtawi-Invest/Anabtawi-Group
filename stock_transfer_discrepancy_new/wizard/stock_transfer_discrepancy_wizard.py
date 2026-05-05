from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class StockTransferDiscrepancyWizard(models.TransientModel):
    _name = "stock.transfer.discrepancy.wizard"
    _description = "Stock Transfer Discrepancy Wizard"

    pick_ids = fields.Many2many("stock.picking", string="Transfers", required=True)
    reason = fields.Text(string="Reason", required=True)

    line_ids = fields.One2many(
        "stock.transfer.discrepancy.wizard.line",
        "wizard_id",
        string="Discrepancies",
        readonly=True,
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        pick_ids = []
        if res.get("pick_ids"):
            # already provided by default_* context
            pick_ids = res["pick_ids"][0][2]
        else:
            ctx_pick_ids = self.env.context.get("button_validate_picking_ids") or self.env.context.get(
                "active_ids"
            )
            if ctx_pick_ids:
                pick_ids = ctx_pick_ids

        if pick_ids and "pick_ids" in fields_list and not res.get("pick_ids"):
            res["pick_ids"] = [(6, 0, pick_ids)]

        if pick_ids and "line_ids" in fields_list:
            lines_cmds = []
            for picking in self.env["stock.picking"].browse(pick_ids):
                for vals in picking._get_transfer_discrepancy_move_vals():
                    lines_cmds.append((0, 0, vals))
            res["line_ids"] = lines_cmds

        return res

    def action_confirm(self):
        self.ensure_one()

        now = fields.Datetime.now()  # This is the picking validation time
        deadline = now + relativedelta(hours=48)

        discrepancies = []
        for line in self.line_ids:
            # Only create if there is an actual difference (safety)
            if line.expected_qty > line.actual_qty:
                discrepancies.append(
                    {
                        "picking_id": line.picking_id.id,
                        "product_id": line.product_id.id,
                        "expected_qty": line.expected_qty,
                        "actual_qty": line.actual_qty,
                        "reason": self.reason,
                        "stage": line.stage,
                        "truck_location_id": line.truck_location_id.id,
                        "driver_id": line.driver_id.id if line.driver_id else False,
                        "responsible_user_id": self.env.user.id,
                        "date": now,
                        "validated_at": now,
                        "investigation_deadline": deadline,
                        "state": "under_investigation",
                    }
                )

        if discrepancies:
            self.env["stock.transfer.discrepancy"].create(discrepancies)

        # Resume normal validation flow (backorder wizards etc.) but skip our wizard.
        pickings_to_validate_ids = self.env.context.get("button_validate_picking_ids") or self.pick_ids.ids
        pickings_to_validate = self.env["stock.picking"].browse(pickings_to_validate_ids)
        return pickings_to_validate.with_context(
            **dict(self.env.context, skip_transfer_discrepancy_wizard=True)
        ).button_validate()


class StockTransferDiscrepancyWizardLine(models.TransientModel):
    _name = "stock.transfer.discrepancy.wizard.line"
    _description = "Stock Transfer Discrepancy Wizard Line"

    wizard_id = fields.Many2one(
        "stock.transfer.discrepancy.wizard", required=True, ondelete="cascade"
    )
    picking_id = fields.Many2one("stock.picking", string="Transfer", required=True)
    product_id = fields.Many2one("product.product", string="Product", required=True)
    expected_qty = fields.Float(string="Expected Qty", required=True, digits="Product Unit")
    actual_qty = fields.Float(string="Actual Qty", required=True, digits="Product Unit")
    difference_qty = fields.Float(string="Difference Qty", required=True, digits="Product Unit")
    truck_location_id = fields.Many2one("stock.location", string="Truck Location", required=True)
    driver_id = fields.Many2one("stock.transfer.driver", string="Driver")
    stage = fields.Selection(
        [
            ("dispatch", "Dispatch"),
            ("receipt", "Receipt"),
        ],
        string="Stage",
        required=True,
    )
