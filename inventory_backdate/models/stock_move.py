from odoo import fields, models, _


class StockMove(models.Model):
    _inherit = "stock.move"

    is_backdated = fields.Boolean(
        string="Backdated",
        copy=False,
        help="This stock move was posted using an inventory Accounting Date instead of today.",
    )

    def _action_done(self, cancel_backorder=False):
        res = super()._action_done(cancel_backorder=cancel_backorder)
        force_date = self.env.context.get("force_period_date")
        if not force_date:
            return res

        done_moves = self.filtered(lambda move: move.state == "done")
        if not done_moves:
            return res

        backdate_dt = self.env["stock.quant"]._inventory_backdate_datetime(force_date)
        reason = self.env.context.get("inventory_backdate_reason") or ""
        done_moves.write({
            "date": backdate_dt,
            "is_backdated": True,
        })
        pickings = done_moves.picking_id
        if pickings:
            pickings.write({"date_done": backdate_dt})
        done_moves._post_inventory_backdate_log(force_date, reason)
        return res

    def _post_inventory_backdate_log(self, accounting_date, reason):
        body = _(
            "Inventory adjustment backdated.\nDate: %(date)s\nUser: %(user)s\nReason: %(reason)s",
            date=accounting_date,
            user=self.env.user.display_name,
            reason=reason or _("Not specified"),
        )
        for picking in self.picking_id:
            picking.message_post(body=body)
        for account_move in self.account_move_id:
            account_move.message_post(body=body)
