from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    backdate_reason = fields.Char(
        string="Backdate Reason",
        copy=False,
        help="Optional reason for forcing the Effective Date.",
    )

    def _get_force_effective_datetime(self):
        """Use a pre-set Effective Date (date_done) when validating."""
        self.ensure_one()
        return self.date_done or False

    def _action_done(self):
        if len(self) > 1 and any(picking.date_done for picking in self):
            for picking in self:
                picking._action_done()
            return True

        effective = False
        reason = ""
        if len(self) == 1:
            effective = self._get_force_effective_datetime()
            reason = self.backdate_reason or ""
            if effective:
                self = self.with_context(
                    force_period_date=fields.Date.to_date(effective),
                    force_effective_datetime=effective,
                    inventory_backdate_reason=reason,
                )

        res = super()._action_done()
        if effective:
            self.with_context(skip_backdate_valuation=True).write({"date_done": effective})
            done_moves = self.move_ids.filtered(lambda move: move.state == "done")
            done_moves.write({"is_backdated": True})
            done_moves._post_inventory_backdate_log(fields.Date.to_date(effective), reason)
            done_moves._sync_backdated_account_move_date(effective)
            done_moves._recompute_backdated_valuation()
        return res

    def write(self, vals):
        res = super().write(vals)
        if vals.get("date_done") and not self.env.context.get("skip_backdate_valuation"):
            done_pickings = self.filtered(lambda picking: picking.state == "done")
            if done_pickings:
                done_moves = done_pickings.move_ids.filtered(lambda move: move.state == "done")
                done_moves.write({"is_backdated": True})
                done_moves._sync_backdated_account_move_date(vals["date_done"])
                done_moves._recompute_backdated_valuation()
        return res
