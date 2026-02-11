from odoo import api, fields, models


class StockTransferDiscrepancy(models.Model):
    _name = "stock.transfer.discrepancy"
    _description = "Stock Transfer Discrepancy"
    _order = "date desc, id desc"

    picking_id = fields.Many2one(
        "stock.picking",
        string="Transfer",
        required=True,
        index=True,
        ondelete="cascade",
    )
    move_id = fields.Many2one(
        "stock.move",
        string="Move",
        required=False,
        index=True,
        ondelete="set null",
    )
    product_id = fields.Many2one(
        "product.product",
        string="Product",
        required=True,
        index=True,
    )
    expected_qty = fields.Float(string="Expected Qty", required=True, digits="Product Unit")
    done_qty = fields.Float(string="Done Qty", required=True, digits="Product Unit")
    difference_qty = fields.Float(string="Difference Qty", required=True, digits="Product Unit")

    reason = fields.Text(string="Reason", required=True)
    stage = fields.Selection(
        [
            ("factory_transit", "Factory→Transit"),
            ("transit_salt", "Transit→Salt"),
        ],
        string="Stage",
        required=True,
        index=True,
    )
    responsible_user_id = fields.Many2one(
        "res.users",
        string="Responsible",
        required=True,
        default=lambda self: self.env.user,
        index=True,
    )
    date = fields.Datetime(string="Date", required=True, default=fields.Datetime.now, index=True)

    company_id = fields.Many2one(
        related="picking_id.company_id",
        store=True,
        readonly=True,
    )

    @api.onchange("expected_qty", "done_qty")
    def _onchange_expected_done_qty(self):
        for rec in self:
            rec.difference_qty = (rec.expected_qty or 0.0) - (rec.done_qty or 0.0)

